"""
Feature: 卡路里打卡（AI估算）
用户输入食物描述 → Claude 估算热量 → 记录到数据库
"""
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership, require_usage_quota
from services.claude_client import call_claude
from db.client import get_client
from db.health import update_challenge_progress

ASK_MEAL_TYPE, ASK_FOOD = range(2)
_KEY = "calorie_estimate"

_MEAL_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("☀️ 早餐", callback_data="clog_breakfast"),
     InlineKeyboardButton("🌞 午餐", callback_data="clog_lunch")],
    [InlineKeyboardButton("🌙 晚餐", callback_data="clog_dinner"),
     InlineKeyboardButton("🥜 加餐", callback_data="clog_snack")],
    [InlineKeyboardButton("❌ 取消", callback_data="cancel_clog")],
])

_MEAL_NAMES = {
    "clog_breakfast": ("breakfast", "早餐"),
    "clog_lunch": ("lunch", "午餐"),
    "clog_dinner": ("dinner", "晚餐"),
    "clog_snack": ("snack", "加餐"),
}


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_clog")]])


def _done_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🥗 继续记录", callback_data="feature_cal_log"),
         InlineKeyboardButton("❤️ 健康打卡", callback_data="feature_health_checkin")],
        [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
    ])


def _get_today_total(user_id: int) -> tuple[int, int]:
    """返回今日已记录的总卡路里和餐数。"""
    db = get_client()
    today = date.today().isoformat()
    result = (
        db.table("calorie_logs")
        .select("estimated_calories")
        .eq("user_id", user_id)
        .eq("log_date", today)
        .execute()
    )
    rows = result.data or []
    total = sum(r.get("estimated_calories", 0) or 0 for r in rows)
    return total, len(rows)


def _save_calorie_log(user_id: int, meal_type: str, food_desc: str,
                      calories: int, protein: float, carbs: float, fat: float):
    """保存卡路里记录并加积分。"""
    db = get_client()
    today = date.today().isoformat()

    db.table("calorie_logs").insert({
        "user_id": user_id,
        "log_date": today,
        "meal_type": meal_type,
        "food_description": food_desc,
        "estimated_calories": calories,
        "estimated_protein": protein,
        "estimated_carbs": carbs,
        "estimated_fat": fat,
    }).execute()

    # +3 积分/餐
    user = db.table("users").select("points").eq("id", user_id).maybe_single().execute()
    new_points = ((user.data or {}).get("points", 0) or 0) + 3
    db.table("users").update({"points": new_points}).eq("id", user_id).execute()

    return new_points


def _parse_calories_from_response(text: str) -> tuple[int, float, float, float]:
    """从 Claude 响应中提取本餐合计数据。"""
    import re
    cal_match = re.search(r"本餐合计[：:]\s*(\d+)", text)
    calories = int(cal_match.group(1)) if cal_match else 0

    p_match = re.search(r"蛋白质\s*[≈≅~]*\s*(\d+(?:\.\d+)?)", text)
    protein = float(p_match.group(1)) if p_match else 0

    c_match = re.search(r"碳水\s*[≈≅~]*\s*(\d+(?:\.\d+)?)", text)
    carbs = float(c_match.group(1)) if c_match else 0

    f_match = re.search(r"脂肪\s*[≈≅~]*\s*(\d+(?:\.\d+)?)", text)
    fat = float(f_match.group(1)) if f_match else 0

    return calories, protein, carbs, fat


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        reply = query.message.reply_text
    else:
        reply = update.message.reply_text

    user_id = update.effective_user.id
    total, count = _get_today_total(user_id)
    status = f"\n📊 今日已记录 {count} 餐，合计 {total}kcal" if count > 0 else ""

    await reply(
        f"🥗 *卡路里打卡*{status}\n\n"
        f"选择你要记录的餐次 👇",
        parse_mode="Markdown",
        reply_markup=_MEAL_KB,
    )
    return ASK_MEAL_TYPE


async def receive_meal_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data not in _MEAL_NAMES:
        return ASK_MEAL_TYPE

    key, name = _MEAL_NAMES[data]
    context.user_data["clog_meal_type"] = key
    context.user_data["clog_meal_name"] = name

    await query.edit_message_text(
        f"🥗 *记录{name}*\n\n"
        f"用自然语言描述你吃了什么：\n\n"
        f"例如：`一碗牛肉面，一个卤蛋，一杯豆浆`",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_FOOD


@require_usage_quota
async def receive_food(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    food_desc = update.message.text.strip()
    if len(food_desc) < 2:
        await update.message.reply_text(
            "⚠️ 请描述你吃了什么，至少写几个字",
            reply_markup=_cancel_kb(),
        )
        return ASK_FOOD

    user_id = update.effective_user.id
    meal_type = context.user_data.get("clog_meal_type", "snack")
    meal_name = context.user_data.get("clog_meal_name", "加餐")

    await update.message.reply_text(f"⏳ 正在估算 *{meal_name}* 热量...", parse_mode="Markdown")

    result = await call_claude(
        _KEY, food_desc,
        user_id=user_id,
        max_tokens=500,
    )

    # 解析并保存
    calories, protein, carbs, fat = _parse_calories_from_response(result)
    new_points = _save_calorie_log(user_id, meal_type, food_desc, calories, protein, carbs, fat)

    # 更新挑战进度
    try:
        update_challenge_progress(user_id, "cal_log_days")
    except Exception:
        pass

    # 今日累计
    today_total, today_count = _get_today_total(user_id)

    # 进度条（假设目标2400kcal）
    target = 2400
    pct = min(today_total / target * 100, 100) if target > 0 else 0
    bar_filled = round(pct / 100 * 15)
    bar = "▓" * bar_filled + "░" * (15 - bar_filled)
    remaining = max(target - today_total, 0)

    await update.message.reply_text(
        f"{result}\n\n"
        f"📊 *今日累计*: {today_total}/{target}kcal ({pct:.0f}%)\n"
        f"{bar} {pct:.0f}%\n\n"
        f"剩余额度: {remaining}kcal\n"
        f"🪙 +3 积分（总计 {new_points}）",
        parse_mode="Markdown",
        reply_markup=_done_kb(),
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q:
        await q.answer()
        await q.edit_message_text("已取消。发送 /menu 返回主菜单。")
    else:
        await update.message.reply_text("已取消。发送 /menu 返回主菜单。")
    return ConversationHandler.END


def build_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("callog", entry),
            CallbackQueryHandler(entry, pattern="^feature_cal_log$"),
        ],
        states={
            ASK_MEAL_TYPE: [CallbackQueryHandler(receive_meal_type, pattern="^clog_")],
            ASK_FOOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_food)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_clog$"),
        ],
        conversation_timeout=180,
        per_user=True, per_chat=True, allow_reentry=True,
    )

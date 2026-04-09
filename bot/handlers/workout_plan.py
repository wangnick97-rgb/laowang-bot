"""
Feature: 今日训练计划（AI生成）
选择目标 → 选择部位 → 选择时间 → Claude 生成计划
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    CallbackQueryHandler, filters,
)
from bot.middleware import require_membership, require_usage_quota
from services.claude_client import call_claude

ASK_GOAL, ASK_BODY, ASK_TIME = range(3)
_KEY = "workout_plan"

_GOAL_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("💪 增肌", callback_data="wo_goal_bulk"),
     InlineKeyboardButton("🔥 减脂", callback_data="wo_goal_cut")],
    [InlineKeyboardButton("⚖️ 维持", callback_data="wo_goal_maintain")],
    [InlineKeyboardButton("❌ 取消", callback_data="cancel_workout")],
])

_BODY_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🫸 推（胸/肩/三头）", callback_data="wo_body_push"),
     InlineKeyboardButton("🫷 拉（背/二头）", callback_data="wo_body_pull")],
    [InlineKeyboardButton("🦵 腿", callback_data="wo_body_legs"),
     InlineKeyboardButton("💪 全身", callback_data="wo_body_full")],
    [InlineKeyboardButton("🏃 有氧/HIIT", callback_data="wo_body_cardio"),
     InlineKeyboardButton("🔥 核心/腹肌", callback_data="wo_body_core")],
    [InlineKeyboardButton("❌ 取消", callback_data="cancel_workout")],
])

_TIME_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("30min", callback_data="wo_time_30"),
     InlineKeyboardButton("45min", callback_data="wo_time_45"),
     InlineKeyboardButton("60min", callback_data="wo_time_60")],
    [InlineKeyboardButton("75min", callback_data="wo_time_75"),
     InlineKeyboardButton("90min", callback_data="wo_time_90")],
    [InlineKeyboardButton("❌ 取消", callback_data="cancel_workout")],
])

_GOAL_NAMES = {"wo_goal_bulk": "增肌", "wo_goal_cut": "减脂", "wo_goal_maintain": "维持"}
_BODY_NAMES = {
    "wo_body_push": "推日（胸/肩/三头）",
    "wo_body_pull": "拉日（背/二头）",
    "wo_body_legs": "腿日",
    "wo_body_full": "全身训练",
    "wo_body_cardio": "有氧/HIIT",
    "wo_body_core": "核心/腹肌",
}


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_workout")]])


def _done_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏃 健身打卡", callback_data="feature_gym_log"),
         InlineKeyboardButton("🍽️ 今日食谱", callback_data="feature_meal")],
        [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
    ])


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        reply = query.message.reply_text
    else:
        reply = update.message.reply_text

    await reply(
        "🏋️ *今日训练计划*\n\n"
        "AI 会根据你的选择生成完整训练方案。\n\n"
        "选择你的训练目标 👇",
        parse_mode="Markdown",
        reply_markup=_GOAL_KB,
    )
    return ASK_GOAL


async def receive_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data not in _GOAL_NAMES:
        return ASK_GOAL

    context.user_data["wo_goal"] = _GOAL_NAMES[data]

    await query.edit_message_text(
        f"🏋️ *今日训练计划*\n\n"
        f"目标：*{_GOAL_NAMES[data]}* ✅\n\n"
        f"今天练哪个部位？",
        parse_mode="Markdown",
        reply_markup=_BODY_KB,
    )
    return ASK_BODY


async def receive_body(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data not in _BODY_NAMES:
        return ASK_BODY

    context.user_data["wo_body"] = _BODY_NAMES[data]

    await query.edit_message_text(
        f"🏋️ *今日训练计划*\n\n"
        f"目标：*{context.user_data['wo_goal']}*\n"
        f"部位：*{_BODY_NAMES[data]}* ✅\n\n"
        f"你有多少时间？",
        parse_mode="Markdown",
        reply_markup=_TIME_KB,
    )
    return ASK_TIME


@require_usage_quota
async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    try:
        minutes = int(data.split("_")[-1])
    except ValueError:
        return ASK_TIME

    goal = context.user_data.get("wo_goal", "增肌")
    body = context.user_data.get("wo_body", "全身训练")

    await query.edit_message_text(
        f"⏳ *正在生成训练计划...*\n\n"
        f"目标：{goal} | 部位：{body} | 时间：{minutes}min",
        parse_mode="Markdown",
    )

    user_msg = f"目标：{goal}\n部位：{body}\n可用时间：{minutes}分钟"
    result = await call_claude(
        _KEY, user_msg,
        user_id=update.effective_user.id,
        max_tokens=1000,
    )

    await query.message.reply_text(result, parse_mode="Markdown", reply_markup=_done_kb())
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
            CommandHandler("workout", entry),
            CallbackQueryHandler(entry, pattern="^feature_workout$"),
        ],
        states={
            ASK_GOAL: [CallbackQueryHandler(receive_goal, pattern="^wo_goal_")],
            ASK_BODY: [CallbackQueryHandler(receive_body, pattern="^wo_body_")],
            ASK_TIME: [CallbackQueryHandler(receive_time, pattern="^wo_time_")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_workout$"),
        ],
        conversation_timeout=120,
        per_user=True, per_chat=True, allow_reentry=True,
    )

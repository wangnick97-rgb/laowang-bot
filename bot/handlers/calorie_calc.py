"""
Feature: 卡路里计算器
Mifflin-St Jeor 公式，纯计算，不调 Claude。
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership

ASK_STATS, ASK_ACTIVITY, ASK_GOAL = range(3)

_ACTIVITY_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🪑 久坐（几乎不运动）", callback_data="cal_act_1.2")],
    [InlineKeyboardButton("🚶 轻度（1-3天/周）", callback_data="cal_act_1.375")],
    [InlineKeyboardButton("🏃 中度（3-5天/周）", callback_data="cal_act_1.55")],
    [InlineKeyboardButton("🏋️ 高强度（6-7天/周）", callback_data="cal_act_1.725")],
    [InlineKeyboardButton("⚡ 极高（体力劳动/双练）", callback_data="cal_act_1.9")],
    [InlineKeyboardButton("❌ 取消", callback_data="cancel_calories")],
])

_GOAL_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("💪 增肌 (+400kcal)", callback_data="cal_goal_bulk"),
     InlineKeyboardButton("🔥 减脂 (-400kcal)", callback_data="cal_goal_cut")],
    [InlineKeyboardButton("⚖️ 维持", callback_data="cal_goal_maintain")],
    [InlineKeyboardButton("❌ 取消", callback_data="cancel_calories")],
])

_GOAL_OFFSET = {
    "cal_goal_bulk": ("增肌", 400),
    "cal_goal_cut": ("减脂", -400),
    "cal_goal_maintain": ("维持", 0),
}

_ACTIVITY_NAMES = {
    1.2: "久坐",
    1.375: "轻度活跃",
    1.55: "中度活跃",
    1.725: "高强度",
    1.9: "极高强度",
}


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_calories")]])


def _done_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧮 蛋白质计算", callback_data="feature_protein"),
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
        "🔥 *卡路里计算器*\n\n"
        "请输入你的基本信息（用空格分隔）：\n\n"
        "`体重(kg) 身高(cm) 年龄`\n\n"
        "例如：`75 178 28`",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_STATS


async def receive_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    parts = text.replace("，", " ").replace(",", " ").split()

    if len(parts) != 3:
        await update.message.reply_text(
            "⚠️ 请输入 3 个数字（体重 身高 年龄），用空格分隔\n"
            "例如：`75 178 28`",
            parse_mode="Markdown",
            reply_markup=_cancel_kb(),
        )
        return ASK_STATS

    try:
        weight = float(parts[0])
        height = float(parts[1])
        age = int(parts[2])
        if not (30 <= weight <= 250 and 100 <= height <= 250 and 10 <= age <= 100):
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "⚠️ 数值不合理，请检查后重新输入\n"
            "体重(30-250kg) 身高(100-250cm) 年龄(10-100)",
            reply_markup=_cancel_kb(),
        )
        return ASK_STATS

    context.user_data["cal_weight"] = weight
    context.user_data["cal_height"] = height
    context.user_data["cal_age"] = age

    await update.message.reply_text(
        f"✅ 体重 *{weight}kg* | 身高 *{height}cm* | 年龄 *{age}岁*\n\n"
        "选择你的活动等级：",
        parse_mode="Markdown",
        reply_markup=_ACTIVITY_KB,
    )
    return ASK_ACTIVITY


async def receive_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data  # cal_act_1.55
    try:
        factor = float(data.split("_")[-1])
    except ValueError:
        return ASK_ACTIVITY

    context.user_data["cal_activity"] = factor

    await query.edit_message_text(
        f"活动等级：*{_ACTIVITY_NAMES.get(factor, str(factor))}* ✅\n\n"
        "选择你的目标：",
        parse_mode="Markdown",
        reply_markup=_GOAL_KB,
    )
    return ASK_GOAL


async def receive_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data
    if data not in _GOAL_OFFSET:
        return ASK_GOAL

    weight = context.user_data.get("cal_weight", 75)
    height = context.user_data.get("cal_height", 178)
    age = context.user_data.get("cal_age", 28)
    factor = context.user_data.get("cal_activity", 1.55)
    goal_name, offset = _GOAL_OFFSET[data]

    # Mifflin-St Jeor (男性)
    bmr = round(10 * weight + 6.25 * height - 5 * age - 5)
    tdee = round(bmr * factor)
    target = tdee + offset

    # 宏量素分配
    protein_g = round(weight * (2.0 if offset >= 0 else 2.2))
    protein_cal = protein_g * 4
    fat_cal = round(target * 0.25)
    fat_g = round(fat_cal / 9)
    carb_cal = target - protein_cal - fat_cal
    carb_g = round(carb_cal / 4)

    # 进度条
    bar_len = 15
    p_bar = round(protein_cal / target * bar_len)
    f_bar = round(fat_cal / target * bar_len)
    c_bar = bar_len - p_bar - f_bar
    bar = "🟦" * p_bar + "🟨" * f_bar + "🟩" * c_bar

    offset_text = f"+{offset}" if offset > 0 else str(offset) if offset < 0 else "±0"

    await query.edit_message_text(
        f"🔥 *卡路里计算结果*\n\n"
        f"📋 *基本信息*\n"
        f"体重: {weight}kg | 身高: {height}cm | 年龄: {age}岁\n"
        f"活动等级: {_ACTIVITY_NAMES.get(factor, '')}\n"
        f"目标: {goal_name} ({offset_text}kcal)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔢 *计算过程*\n"
        f"BMR（基础代谢）: {bmr} kcal\n"
        f"TDEE（日消耗）: {tdee} kcal\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 *每日目标: {target} kcal*\n\n"
        f"🥩 蛋白质: {protein_g}g ({protein_cal}kcal)\n"
        f"🧈 脂肪: {fat_g}g ({fat_cal}kcal)\n"
        f"🍚 碳水: {carb_g}g ({carb_cal}kcal)\n\n"
        f"{bar}\n"
        f"🟦蛋白质 🟨脂肪 🟩碳水\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ *老王说：数字不会骗你。算清楚，执行到位，身体会给你答案。*",
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
            CommandHandler("calories", entry),
            CallbackQueryHandler(entry, pattern="^feature_calories$"),
        ],
        states={
            ASK_STATS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_stats)],
            ASK_ACTIVITY: [CallbackQueryHandler(receive_activity, pattern="^cal_act_")],
            ASK_GOAL: [CallbackQueryHandler(receive_goal, pattern="^cal_goal_")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_calories$"),
        ],
        conversation_timeout=120,
        per_user=True, per_chat=True, allow_reentry=True,
    )

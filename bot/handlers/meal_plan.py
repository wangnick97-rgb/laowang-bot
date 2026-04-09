"""
Feature: 今日食谱（AI生成）
选择目标 → 输入体重 → 选择偏好 → Claude 生成三餐+加餐
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership, require_usage_quota
from services.claude_client import call_claude

ASK_GOAL, ASK_WEIGHT, ASK_PREF = range(3)
_KEY = "meal_plan"

_GOAL_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("💪 增肌", callback_data="meal_goal_bulk"),
     InlineKeyboardButton("🔥 减脂", callback_data="meal_goal_cut")],
    [InlineKeyboardButton("⚖️ 维持", callback_data="meal_goal_maintain")],
    [InlineKeyboardButton("❌ 取消", callback_data="cancel_meal")],
])

_PREF_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🍖 无限制", callback_data="meal_pref_none")],
    [InlineKeyboardButton("🚫🐷 不吃猪肉", callback_data="meal_pref_no_pork"),
     InlineKeyboardButton("🥦 素食", callback_data="meal_pref_veg")],
    [InlineKeyboardButton("🥜 低碳水", callback_data="meal_pref_lowcarb"),
     InlineKeyboardButton("🍚 中式为主", callback_data="meal_pref_chinese")],
    [InlineKeyboardButton("❌ 取消", callback_data="cancel_meal")],
])

_GOAL_NAMES = {"meal_goal_bulk": "增肌", "meal_goal_cut": "减脂", "meal_goal_maintain": "维持"}
_PREF_NAMES = {
    "meal_pref_none": "无限制",
    "meal_pref_no_pork": "不吃猪肉",
    "meal_pref_veg": "素食",
    "meal_pref_lowcarb": "低碳水",
    "meal_pref_chinese": "中式为主",
}


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_meal")]])


def _done_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧮 蛋白质计算", callback_data="feature_protein"),
         InlineKeyboardButton("🏋️ 今日训练", callback_data="feature_workout")],
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
        "🍽️ *今日食谱*\n\n"
        "AI 会为你生成精确到克的三餐+加餐方案。\n\n"
        "选择你的饮食目标 👇",
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

    context.user_data["meal_goal"] = _GOAL_NAMES[data]

    await query.edit_message_text(
        f"🍽️ *今日食谱*\n\n"
        f"目标：*{_GOAL_NAMES[data]}* ✅\n\n"
        f"请输入你的体重（kg）：\n"
        f"例如：`75`",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_WEIGHT


async def receive_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        weight = float(text)
        if weight < 30 or weight > 250:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "⚠️ 请输入有效体重（30-250kg），例如：`75`",
            parse_mode="Markdown",
            reply_markup=_cancel_kb(),
        )
        return ASK_WEIGHT

    context.user_data["meal_weight"] = weight

    await update.message.reply_text(
        f"体重：*{weight}kg* ✅\n\n"
        f"选择饮食偏好：",
        parse_mode="Markdown",
        reply_markup=_PREF_KB,
    )
    return ASK_PREF


@require_usage_quota
async def receive_pref(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data not in _PREF_NAMES:
        return ASK_PREF

    goal = context.user_data.get("meal_goal", "增肌")
    weight = context.user_data.get("meal_weight", 75)
    pref = _PREF_NAMES[data]

    await query.edit_message_text(
        f"⏳ *正在生成食谱...*\n\n"
        f"目标：{goal} | 体重：{weight}kg | 偏好：{pref}",
        parse_mode="Markdown",
    )

    user_msg = f"目标：{goal}\n体重：{weight}kg\n饮食偏好：{pref}"
    result = await call_claude(
        _KEY, user_msg,
        user_id=update.effective_user.id,
        max_tokens=1200,
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
            CommandHandler("meal", entry),
            CallbackQueryHandler(entry, pattern="^feature_meal$"),
        ],
        states={
            ASK_GOAL: [CallbackQueryHandler(receive_goal, pattern="^meal_goal_")],
            ASK_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_weight)],
            ASK_PREF: [CallbackQueryHandler(receive_pref, pattern="^meal_pref_")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_meal$"),
        ],
        conversation_timeout=120,
        per_user=True, per_chat=True, allow_reentry=True,
    )

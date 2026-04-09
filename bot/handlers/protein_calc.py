"""
Feature: 蛋白质需求计算器
纯计算，不调 Claude。输入体重+目标 → 输出蛋白质需求。
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership

ASK_WEIGHT, ASK_GOAL = range(2)

_GOAL_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("💪 增肌", callback_data="protein_bulk"),
     InlineKeyboardButton("🔥 减脂", callback_data="protein_cut")],
    [InlineKeyboardButton("⚖️ 维持", callback_data="protein_maintain")],
    [InlineKeyboardButton("❌ 取消", callback_data="cancel_protein")],
])

_GOAL_MULTIPLIER = {
    "protein_bulk": ("增肌", 2.0),
    "protein_cut": ("减脂", 2.2),
    "protein_maintain": ("维持", 1.6),
}

# 每100g食物的蛋白质含量
_FOOD_PROTEIN = [
    ("鸡胸肉 200g", 46),
    ("鸡蛋 3个", 18),
    ("希腊酸奶 200g", 20),
    ("蛋白粉 1勺", 25),
    ("牛肉 150g", 38),
    ("三文鱼 150g", 30),
    ("豆腐 200g", 16),
]


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_protein")]])


def _done_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🍽️ 今日食谱", callback_data="feature_meal"),
         InlineKeyboardButton("🔥 卡路里计算", callback_data="feature_calories")],
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
        "🧮 *蛋白质需求计算器*\n\n"
        "请输入你的体重（kg）：\n\n"
        "例如：`75`",
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

    context.user_data["protein_weight"] = weight
    await update.message.reply_text(
        f"体重：*{weight}kg* ✅\n\n"
        "选择你的目标：",
        parse_mode="Markdown",
        reply_markup=_GOAL_KB,
    )
    return ASK_GOAL


async def receive_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data
    if data not in _GOAL_MULTIPLIER:
        return ASK_GOAL

    weight = context.user_data.get("protein_weight", 75)
    goal_name, multiplier = _GOAL_MULTIPLIER[data]
    protein_need = round(weight * multiplier)

    # 生成食物组合建议
    combo = []
    remaining = protein_need
    for food, protein in _FOOD_PROTEIN:
        if remaining <= 0:
            break
        combo.append(f"├── {food} = {protein}g蛋白质")
        remaining -= protein

    combo_total = protein_need - remaining
    combo_text = "\n".join(combo)

    await query.edit_message_text(
        f"🧮 *蛋白质需求计算*\n\n"
        f"体重: *{weight}kg* | 目标: *{goal_name}*\n"
        f"系数: {multiplier}g/kg\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *每日蛋白质需求: {protein_need}g*\n\n"
        f"💡 *怎么吃到{protein_need}g？*\n"
        f"{combo_text}\n"
        f"└── 合计 ≈ {combo_total}g ✅\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ *老王说：蛋白质是肌肉的砖头。少一块，墙就矮一层。*",
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
            CommandHandler("protein", entry),
            CallbackQueryHandler(entry, pattern="^feature_protein$"),
        ],
        states={
            ASK_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_weight)],
            ASK_GOAL: [CallbackQueryHandler(receive_goal, pattern="^protein_")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_protein$"),
        ],
        conversation_timeout=120,
        per_user=True, per_chat=True, allow_reentry=True,
    )

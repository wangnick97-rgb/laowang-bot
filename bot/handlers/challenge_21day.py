"""
Feature: 21天挑战
Simple static + redirect handler. Shows 5 preset challenge categories
and links to the existing /challenge system.
No ConversationHandler needed.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from bot.middleware import require_membership

_CHALLENGES = [
    ("📚", "21天阅读挑战", "每天阅读30分钟，坚持21天"),
    ("✍️", "21天写作挑战", "每天写300字以上，坚持21天"),
    ("🌅", "21天早起挑战", "每天7点前起床，坚持21天"),
    ("📵", "21天无社媒挑战", "每天社交媒体使用<30分钟，坚持21天"),
    ("🧘", "21天冥想挑战", "每天冥想10分钟，坚持21天"),
]


def _main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 查看/加入挑战", callback_data="feature_challenge")],
        [InlineKeyboardButton("🔥 深度工作打卡", callback_data="feature_deep_work"),
         InlineKeyboardButton("📋 今日计划", callback_data="feature_daily_plan")],
        [InlineKeyboardButton("← 执行系统", callback_data="menu_execution")],
    ])


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        reply = query.message.reply_text
    else:
        reply = update.message.reply_text

    lines = [
        "🏆 *21天挑战*\n",
        "研究表明，坚持21天就能初步建立一个新习惯。",
        "选择一个挑战，用21天改变自己：\n",
    ]

    for emoji, title, desc in _CHALLENGES:
        lines.append(f"{emoji} *{title}*\n   {desc}\n")

    lines.append(
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "点击下方按钮查看当前活跃挑战并加入 👇\n\n"
        "⚡ *老王说：21天不长，但足以让你变成另一个人。关键是第一天。*"
    )

    await reply(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=_main_kb(),
    )

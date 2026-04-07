"""
Feature: 爆款选题生成 (Viral Topic Generator)
Single-step: user sends one message → Claude returns 5 viral topic ideas.

Flow:
  Entry → ASK_INPUT → [Claude] → END
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from bot.middleware import require_membership, require_usage_quota
from services.claude_client import call_claude

ASK_INPUT = 0
FEATURE_KEY = "viral_topic"


def _cancel_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ 取消", callback_data="cancel_topic")
    ]])


def _back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔥 再生成一批", callback_data="feature_topic"),
        InlineKeyboardButton("← 主菜单", callback_data="menu_main"),
    ]])


@require_membership
async def entry_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        reply_fn = query.message.reply_text
    else:
        reply_fn = update.message.reply_text

    await reply_fn(
        "🔥 *爆款选题生成*\n\n"
        "告诉我你的垂直领域和目标受众，我来给你生成 5 个爆款选题。\n\n"
        "格式示例：\n"
        "• 投资理财，受众是刚入门的散户\n"
        "• Airbnb 运营，面向想做副业的上班族\n"
        "• AI 工具，面向创业者和自由职业者\n\n"
        "发给我你的方向 👇",
        parse_mode="Markdown",
        reply_markup=_cancel_button(),
    )
    return ASK_INPUT


@require_usage_quota
async def generate_topics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text.strip()
    await update.message.reply_text("🔥 正在生成爆款选题，稍等...")

    result = await call_claude(
        FEATURE_KEY,
        user_input,
        user_id=update.effective_user.id,
        max_tokens=1000,
    )

    await update.message.reply_text(
        result,
        parse_mode="Markdown",
        reply_markup=_back_button(),
    )
    return ConversationHandler.END


async def cancel_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("已取消。发送 /menu 返回主菜单。")
    else:
        await update.message.reply_text("已取消。发送 /menu 返回主菜单。")
    return ConversationHandler.END


def build_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("topic", entry_topic),
            CallbackQueryHandler(entry_topic, pattern="^feature_topic$"),
        ],
        states={
            ASK_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_topics)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_topic),
            CommandHandler("menu", cancel_topic),
            CallbackQueryHandler(cancel_topic, pattern="^cancel_topic$"),
        ],
        conversation_timeout=180,
        per_user=True,
        per_chat=True,
        allow_reentry=True,
    )

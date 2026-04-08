"""
Feature: 短视频脚本生成
Flow: entry → ASK_INPUT → generate → END
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership, require_usage_quota
from services.claude_client import call_claude

ASK_INPUT = 0
_KEY = "script_gen"


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_script")]])

def _done_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✍️ 再写一篇", callback_data="feature_script"),
        InlineKeyboardButton("← 主菜单", callback_data="menu_main"),
    ]])


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    reply = query.message.reply_text if query else update.message.reply_text
    if query:
        await query.answer()
    await reply(
        "✍️ *短视频脚本生成*\n\n"
        "告诉我视频的主题或标题，我来写口播稿 + 直播展开逻辑。\n\n"
        "示例：\n"
        "• 普通人如何用 AI 副业月入 2 万\n"
        "• 新手怎么开始做 Airbnb\n"
        "• 3 个让你下单的销售话术\n\n"
        "发给我你的主题 👇",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_INPUT


@require_usage_quota
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("✍️ 正在生成脚本，稍等...")
    result = await call_claude(_KEY, update.message.text.strip(),
                               user_id=update.effective_user.id, max_tokens=1500)
    await update.message.reply_text(result, parse_mode="Markdown", reply_markup=_done_kb())
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
            CommandHandler("script", entry),
            CallbackQueryHandler(entry, pattern="^feature_script$"),
        ],
        states={ASK_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate)]},
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_script$"),
        ],
        conversation_timeout=180,
        per_user=True, per_chat=True, allow_reentry=True,
    )

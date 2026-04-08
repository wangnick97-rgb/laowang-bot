"""
Feature: 销售话术 / 合同分析
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
_KEY = "sales_assist"


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_sales")]])

def _done_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 再分析一份", callback_data="feature_sales"),
        InlineKeyboardButton("← 主菜单", callback_data="menu_main"),
    ]])


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    reply = query.message.reply_text if query else update.message.reply_text
    if query:
        await query.answer()
    await reply(
        "📋 *销售话术 & 合同分析*\n\n"
        "把下面任意一种内容发给我，我来帮你分析和优化：\n\n"
        "• 合同条款（粘贴关键条款）\n"
        "• 合作邀约（收到的邀请文字）\n"
        "• 客户消息（不知道怎么回复）\n"
        "• 谈判对话（想要分析策略）\n\n"
        "发给我 👇",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_INPUT


@require_usage_quota
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("📋 正在分析，稍等...")
    result = await call_claude(_KEY, update.message.text.strip(),
                               user_id=update.effective_user.id, max_tokens=1200)
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
            CommandHandler("sales", entry),
            CallbackQueryHandler(entry, pattern="^feature_sales$"),
        ],
        states={ASK_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate)]},
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_sales$"),
        ],
        conversation_timeout=300,
        per_user=True, per_chat=True, allow_reentry=True,
    )

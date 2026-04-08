"""
Feature: 品牌定位
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
_KEY = "brand_positioning"


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_brand")]])

def _done_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 重新定位", callback_data="feature_brand"),
        InlineKeyboardButton("← 主菜单", callback_data="menu_main"),
    ]])


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    reply = query.message.reply_text if query else update.message.reply_text
    if query:
        await query.answer()
    await reply(
        "🏷️ *个人品牌定位*\n\n"
        "告诉我你的背景，我帮你找到最有竞争力的差异化定位。\n\n"
        "请包含：\n"
        "• 你的经历/专业领域\n"
        "• 目标客户是谁\n"
        "• 想做什么（自媒体/咨询/课程/其他）\n\n"
        "发给我你的情况 👇",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_INPUT


@require_usage_quota
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🏷️ 正在分析定位，稍等...")
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
            CommandHandler("brand", entry),
            CallbackQueryHandler(entry, pattern="^feature_brand$"),
        ],
        states={ASK_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate)]},
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_brand$"),
        ],
        conversation_timeout=180,
        per_user=True, per_chat=True, allow_reentry=True,
    )

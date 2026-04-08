"""
Feature: 房东/客人沟通话术
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
_KEY = "landlord_msg"


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_landlord")]])

def _done_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 再写一条", callback_data="feature_landlord"),
        InlineKeyboardButton("← 主菜单", callback_data="menu_main"),
    ]])


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    reply = query.message.reply_text if query else update.message.reply_text
    if query:
        await query.answer()
    await reply(
        "💬 *房东 & 客人沟通话术*\n\n"
        "描述你遇到的场景，我来写可以直接发的话术。\n\n"
        "常见场景：\n"
        "• 跟房东续租谈价\n"
        "• 客人投诉，需要安抚\n"
        "• 处理差评（想礼貌回复）\n"
        "• 催客人结账或退房\n"
        "• 拒绝不合适的客人\n\n"
        "发给我你的场景 👇",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_INPUT


@require_usage_quota
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("💬 正在生成话术，稍等...")
    result = await call_claude(_KEY, update.message.text.strip(),
                               user_id=update.effective_user.id, max_tokens=800)
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
            CommandHandler("landlord", entry),
            CallbackQueryHandler(entry, pattern="^feature_landlord$"),
        ],
        states={ASK_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate)]},
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_landlord$"),
        ],
        conversation_timeout=180,
        per_user=True, per_chat=True, allow_reentry=True,
    )

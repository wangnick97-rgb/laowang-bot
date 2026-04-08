"""
Feature: Airbnb 房源诊断
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
_KEY = "property_diag"


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_property")]])

def _done_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 再诊断一套", callback_data="feature_property"),
        InlineKeyboardButton("← 主菜单", callback_data="menu_main"),
    ]])


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    reply = query.message.reply_text if query else update.message.reply_text
    if query:
        await query.answer()
    await reply(
        "🏠 *Airbnb 房源诊断*\n\n"
        "告诉我你的房源情况，我来评估可行性和给出建议。\n\n"
        "请包含：\n"
        "• 城市和区域\n"
        "• 月租成本（或房价）\n"
        "• 户型（几室几厅，面积）\n"
        "• 目标平台\n\n"
        "示例：洛杉矶 Santa Monica，月租 $3500，2房1厅 800sqft，目标 Airbnb\n\n"
        "发给我 👇",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_INPUT


@require_usage_quota
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🏠 正在诊断房源，稍等...")
    result = await call_claude(_KEY, update.message.text.strip(),
                               user_id=update.effective_user.id, max_tokens=1000)
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
            CommandHandler("property", entry),
            CallbackQueryHandler(entry, pattern="^feature_property$"),
        ],
        states={ASK_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate)]},
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_property$"),
        ],
        conversation_timeout=180,
        per_user=True, per_chat=True, allow_reentry=True,
    )

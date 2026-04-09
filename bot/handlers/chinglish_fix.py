"""
Feature: 中式英语改写
Flow: entry → ASK_CHINGLISH (user pastes text) → Claude rewrites → END
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership, require_usage_quota
from services.claude_client import call_claude

ASK_CHINGLISH = 0
_KEY = "chinglish_fix"


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_chinglish")]])


def _done_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 再改一段", callback_data="feature_chinglish_fix"),
         InlineKeyboardButton("← 英语系统", callback_data="menu_english")],
        [InlineKeyboardButton("← 个人成长", callback_data="menu_growth")],
    ])


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    reply = query.message.reply_text if query else update.message.reply_text
    if query:
        await query.answer()
    await reply(
        "🔄 *中式英语改写*\n\n"
        "把你写的英文发给我，我来帮你改成地道的表达。\n\n"
        "常见场景：\n"
        "• 工作邮件\n"
        "• LinkedIn 动态\n"
        "• 和老外的聊天消息\n"
        "• 简历/求职信\n\n"
        "直接粘贴你的英文内容 👇",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_CHINGLISH


@require_usage_quota
async def rewrite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_text = update.message.text.strip()

    prompt = (
        f"用户发来了一段可能有中式英语问题的文本：\n\n"
        f"\"{user_text}\"\n\n"
        f"请你：\n"
        f"1. 改写成地道的英文（保持原意）\n"
        f"2. 逐条列出你改了哪些地方，每条用「❌ 原文 → ✅ 改写」的格式\n"
        f"3. 简要解释为什么原文听起来不地道\n"
        f"4. 如果原文已经很好，也要说明\n\n"
        f"用中文解释，英文部分保持英文。格式清晰易读。"
    )

    await update.message.reply_text("🔄 正在改写，稍等...")
    result = await call_claude(_KEY, prompt, user_id=user_id, max_tokens=800)
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
            CommandHandler("chinglish", entry),
            CallbackQueryHandler(entry, pattern="^feature_chinglish_fix$"),
        ],
        states={ASK_CHINGLISH: [MessageHandler(filters.TEXT & ~filters.COMMAND, rewrite)]},
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_chinglish$"),
        ],
        conversation_timeout=180,
        per_user=True, per_chat=True, allow_reentry=True,
    )

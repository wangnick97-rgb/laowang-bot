"""
Feature: 拖延破解器
Flow: entry -> ASK_TASK -> generate -> END
User describes what they're procrastinating -> Claude breaks it into 5-min micro-steps.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership, require_usage_quota
from services.claude_client import call_claude

ASK_TASK = 0
_KEY = "procrastination_breaker"


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_procr")]])


def _done_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 破解另一个", callback_data="feature_procrastination"),
         InlineKeyboardButton("🔥 开始深度工作", callback_data="feature_deep_work")],
        [InlineKeyboardButton("← 执行系统", callback_data="menu_execution")],
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
        "🧊 *拖延破解器*\n\n"
        "告诉我你一直在拖延的那件事，我来帮你：\n\n"
        "• 分析你拖延的真正原因\n"
        "• 拆成 5 分钟就能启动的微步骤\n"
        "• 制定今天和明天的行动计划\n\n"
        "比如：`写年终总结报告` 或 `开始学Python` 或 `整理房间`\n\n"
        "说吧，你在拖什么？👇",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_TASK


@require_usage_quota
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🧠 正在分析拖延模式，拆解微步骤...")
    user_text = update.message.text.strip()
    user_id = update.effective_user.id

    prompt = (
        "用户一直在拖延一件事，需要你帮他破解拖延、立刻行动。\n\n"
        f"用户在拖延的事：\n{user_text}"
    )

    result = await call_claude(_KEY, prompt, user_id=user_id, max_tokens=1500)

    await update.message.reply_text(
        f"{result}",
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
            CommandHandler("unstuck", entry),
            CallbackQueryHandler(entry, pattern="^feature_procrastination$"),
        ],
        states={ASK_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate)]},
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_procr$"),
        ],
        conversation_timeout=300,
        per_user=True, per_chat=True, allow_reentry=True,
    )

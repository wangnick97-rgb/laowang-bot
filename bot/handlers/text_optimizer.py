"""
Feature: 表达优化器
Flow: entry → ASK_TEXT → generate → END
Evaluates Chinese text on 4 dimensions (逻辑/节奏/用词/情绪), outputs optimized version + scores + tips.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership, require_usage_quota
from services.claude_client import call_claude

ASK_TEXT = 0
_KEY = "text_optimizer"


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_text_opt")]])

def _done_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 再优化一段", callback_data="feature_text_optimizer"),
        InlineKeyboardButton("← 表达系统", callback_data="menu_expression"),
    ]])


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    reply = query.message.reply_text if query else update.message.reply_text
    if query:
        await query.answer()
    await reply(
        "✨ *表达优化器*\n\n"
        "把你的中文文本粘贴给我，我会从 4 个维度评估并优化：\n\n"
        "• 逻辑 — 论点是否清晰、连贯\n"
        "• 节奏 — 句子长短搭配、段落呼吸感\n"
        "• 用词 — 精准度、画面感、避免口水词\n"
        "• 情绪 — 感染力、读者共鸣\n\n"
        "每项评分 /10，并给出优化版本 + 改进建议。\n\n"
        "发给我你的文本 👇",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_TEXT


@require_usage_quota
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("✨ 正在评估并优化，稍等...")
    user_text = update.message.text.strip()
    prompt = (
        "你是一位中文表达优化专家。请对以下文本进行评估和优化。\n\n"
        "评估维度（每项 /10 分）：\n"
        "1. 逻辑 — 论点是否清晰、推理是否连贯\n"
        "2. 节奏 — 句子长短搭配、段落呼吸感\n"
        "3. 用词 — 精准度、画面感、是否有口水词\n"
        "4. 情绪 — 感染力、是否引发读者共鸣\n\n"
        "请输出：\n"
        "① 四维评分 + 总分\n"
        "② 优化后的完整版本\n"
        "③ 3-5 条具体改进建议\n\n"
        f"原文：\n{user_text}"
    )
    result = await call_claude(_KEY, prompt,
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
            CommandHandler("optimize", entry),
            CallbackQueryHandler(entry, pattern="^feature_text_optimizer$"),
        ],
        states={ASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate)]},
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_text_opt$"),
        ],
        conversation_timeout=300,
        per_user=True, per_chat=True, allow_reentry=True,
    )

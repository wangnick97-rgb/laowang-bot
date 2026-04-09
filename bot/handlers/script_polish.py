"""
Feature: 口播稿优化
Flow: entry → ASK_SCRIPT → generate → END
Evaluates script (开头钩子/节奏/结构/CTA), outputs polished version with scores.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership, require_usage_quota
from services.claude_client import call_claude

ASK_SCRIPT = 0
_KEY = "script_polish"


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_script_pol")]])

def _done_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 再优化一篇", callback_data="feature_script_polish"),
        InlineKeyboardButton("← 表达系统", callback_data="menu_expression"),
    ]])


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    reply = query.message.reply_text if query else update.message.reply_text
    if query:
        await query.answer()
    await reply(
        "🎙️ *口播稿优化*\n\n"
        "把你的口播稿粘贴给我，我会从 4 个维度评估并打磨：\n\n"
        "• 开头钩子 — 前 3 秒能不能留住人\n"
        "• 节奏 — 长短句交替、停顿点设计\n"
        "• 结构 — 起承转合是否清晰\n"
        "• CTA — 结尾引导是否有力\n\n"
        "每项评分 /10，并输出优化后的完整稿件。\n\n"
        "发给我你的口播稿 👇",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_SCRIPT


@require_usage_quota
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🎙️ 正在评估并优化口播稿，稍等...")
    user_text = update.message.text.strip()
    prompt = (
        "你是一位短视频口播稿优化专家。请对以下口播稿进行评估和优化。\n\n"
        "评估维度（每项 /10 分）：\n"
        "1. 开头钩子 — 前 3 秒是否抓人，能不能留住观众\n"
        "2. 节奏 — 长短句交替、停顿点、是否适合口播\n"
        "3. 结构 — 起承转合是否清晰、信息密度是否合理\n"
        "4. CTA — 结尾行动引导是否有力（点赞/关注/评论）\n\n"
        "请输出：\n"
        "① 四维评分 + 总分\n"
        "② 优化后的完整口播稿（标注停顿点和重音）\n"
        "③ 3-5 条具体改进建议\n\n"
        f"原稿：\n{user_text}"
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
            CommandHandler("polish", entry),
            CallbackQueryHandler(entry, pattern="^feature_script_polish$"),
        ],
        states={ASK_SCRIPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate)]},
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_script_pol$"),
        ],
        conversation_timeout=300,
        per_user=True, per_chat=True, allow_reentry=True,
    )

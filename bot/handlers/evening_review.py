"""
Feature: 晚间复盘 (Evening Review)
展示3个固定复盘问题 → 用户一条消息回答 → Claude 总结 + 反馈 → +5 积分
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership, require_usage_quota
from services.claude_client import call_claude
from db.client import get_client

ASK_REVIEW = 0
_KEY = "evening_review"


def _cancel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ 取消", callback_data="cancel_evening_review")],
    ])


def _done_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💡 认知系统", callback_data="menu_cognition"),
         InlineKeyboardButton("← 主菜单", callback_data="menu_main")],
    ])


# ── Entry ─────────────────────────────────────────────────────────────────────

@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    reply = query.message.reply_text if query else update.message.reply_text
    if query:
        await query.answer()

    await reply(
        "🌙 *晚间复盘*\n\n"
        "每天3个问题，帮你把经验变成能力。\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "请回答以下 3 个问题（一条消息写完即可）：\n\n"
        "1️⃣ *今天最大的收获是什么？*\n"
        "（一件事、一个认知、一次对话都行）\n\n"
        "2️⃣ *今天最大的浪费是什么？*\n"
        "（时间、精力、注意力的浪费）\n\n"
        "3️⃣ *明天最重要的一件事是什么？*\n"
        "（只挑一件，必须具体可执行）\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "一条消息写完三个回答 👇",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_REVIEW


# ── Respond ───────────────────────────────────────────────────────────────────

@require_usage_quota
async def respond(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_input = (
        "用户的晚间复盘回答（三个问题：今天最大收获 / 今天最大浪费 / 明天最重要的一件事）：\n\n"
        + update.message.text.strip()
    )

    await update.message.reply_text("🌙 老王正在看你的复盘...")

    result = await call_claude(_KEY, user_input, user_id=user_id, max_tokens=600)

    # Award 5 points
    try:
        db = get_client()
        user = db.table("users").select("points").eq("id", user_id).maybe_single().execute()
        new_points = ((user.data or {}).get("points", 0) or 0) + 5
        db.table("users").update({"points": new_points}).eq("id", user_id).execute()
        points_text = f"\n\n🪙 +5 积分（复盘奖励）"
    except Exception:
        points_text = ""

    await update.message.reply_text(
        result + points_text,
        parse_mode="Markdown",
        reply_markup=_done_kb(),
    )
    return ConversationHandler.END


# ── Cancel ────────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q:
        await q.answer()
        await q.edit_message_text("已取消。发送 /menu 返回主菜单。")
    else:
        await update.message.reply_text("已取消。发送 /menu 返回主菜单。")
    return ConversationHandler.END


# ── Handler factory ───────────────────────────────────────────────────────────

def build_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("review", entry),
            CallbackQueryHandler(entry, pattern="^feature_evening_review$"),
        ],
        states={
            ASK_REVIEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, respond)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_evening_review$"),
        ],
        conversation_timeout=300,
        per_user=True,
        per_chat=True,
        allow_reentry=True,
    )

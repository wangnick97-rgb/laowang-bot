"""
Feature: 今日计划
Flow: entry -> ASK_TASKS -> generate -> END
User writes 3 most important tasks -> Claude evaluates priority (P0/P1/P2) + scheduling advice.
Awards 3 points.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership, require_usage_quota
from services.claude_client import call_claude
from db.client import get_client
from db.points import get_points_info

ASK_TASKS = 0
_KEY = "daily_plan"

_WANG_QUOTES = [
    "计划不是用来看的，是用来执行的。写下来只是第一步。",
    "每天只做三件事，但每件都做到位，一年下来你会甩开99%的人。",
    "别贪多。三件事做完，你今天就赢了。",
    "真正的高手不是做得多，是砍得狠。P0以外的，都是噪音。",
    "先做最难的那件。拖到下午你就不想做了。",
    "写下计划的人，完成率比不写的高42%。这不是鸡汤，是研究数据。",
]


def _get_quote(user_id: int) -> str:
    from datetime import date
    idx = (user_id + date.today().toordinal()) % len(_WANG_QUOTES)
    return _WANG_QUOTES[idx]


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_plan")]])


def _done_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 重新规划", callback_data="feature_daily_plan"),
         InlineKeyboardButton("🔥 开始深度工作", callback_data="feature_deep_work")],
        [InlineKeyboardButton("← 执行系统", callback_data="menu_execution")],
    ])


def _add_points(user_id: int, amount: int) -> int:
    """Add points to user, return new total."""
    db = get_client()
    info = get_points_info(user_id)
    new_total = (info.get("points", 0) or 0) + amount
    db.table("users").update({"points": new_total}).eq("id", user_id).execute()
    return new_total


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        reply = query.message.reply_text
    else:
        reply = update.message.reply_text

    await reply(
        "📋 *今日计划*\n\n"
        "写下你今天最重要的 *3 件事*，我来帮你：\n\n"
        "• 评估优先级（P0 / P1 / P2）\n"
        "• 给出最佳执行顺序\n"
        "• 安排时间块建议\n\n"
        "格式随意，比如：\n"
        "`1. 完成方案PPT\n2. 跟客户打电话\n3. 健身1小时`\n\n"
        "发给我你的 3 件事 👇",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_TASKS


@require_usage_quota
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("⏳ 正在分析优先级和排程...")
    user_text = update.message.text.strip()
    user_id = update.effective_user.id

    prompt = (
        "用户写下了今天要做的事情。请帮他做优先级评估和时间安排。\n\n"
        f"用户输入：\n{user_text}"
    )

    result = await call_claude(_KEY, prompt, user_id=user_id, max_tokens=1200)

    # Award points
    new_total = _add_points(user_id, 3)
    quote = _get_quote(user_id)

    await update.message.reply_text(
        f"{result}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🪙 +3 积分（总计 {new_total}）\n\n"
        f"⚡ *老王说：{quote}*",
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
            CommandHandler("plan", entry),
            CallbackQueryHandler(entry, pattern="^feature_daily_plan$"),
        ],
        states={ASK_TASKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate)]},
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_plan$"),
        ],
        conversation_timeout=300,
        per_user=True, per_chat=True, allow_reentry=True,
    )

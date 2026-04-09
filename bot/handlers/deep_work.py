"""
Feature: 深度工作打卡
Flow: entry -> select duration via callback buttons -> record + award points -> END
No Claude call needed - pure recording.
Awards 5 points per session, bonus +10 if daily total > 2 hours.
"""
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    CallbackQueryHandler,
)
from bot.middleware import require_membership
from db.client import get_client
from db.points import get_points_info

ASK_DURATION = 0

_DURATION_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("25min 🍅", callback_data="dw_dur_25"),
     InlineKeyboardButton("45min", callback_data="dw_dur_45"),
     InlineKeyboardButton("60min", callback_data="dw_dur_60")],
    [InlineKeyboardButton("90min 🔥", callback_data="dw_dur_90"),
     InlineKeyboardButton("120min 💎", callback_data="dw_dur_120")],
    [InlineKeyboardButton("❌ 取消", callback_data="cancel_deep_work")],
])

_WANG_QUOTES = [
    "深度工作是这个时代最稀缺的能力。你刚才做到了。",
    "手机可以等，你的人生等不了。",
    "专注2小时，顶别人一整天。这就是高手和普通人的差距。",
    "当别人在刷短视频的时候，你在创造价值。差距就是这么拉开的。",
    "心流状态是免费的毒品，而且越用越强。",
    "90分钟不被打断，你就能进入别人一辈子到不了的思维深度。",
]


def _get_quote(user_id: int) -> str:
    idx = (user_id + date.today().toordinal()) % len(_WANG_QUOTES)
    return _WANG_QUOTES[idx]


def _done_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 再来一轮", callback_data="feature_deep_work"),
         InlineKeyboardButton("📋 做个计划", callback_data="feature_daily_plan")],
        [InlineKeyboardButton("← 执行系统", callback_data="menu_execution")],
    ])


def _get_daily_focus_minutes(user_id: int) -> int:
    """Get total deep work minutes for today from user_data stored in context.
    We use a simple DB approach: store in a focus_logs-style pattern via users table metadata."""
    db = get_client()
    today = date.today().isoformat()
    # Try to read today's focus total from a simple tracking table
    try:
        result = (
            db.table("focus_logs")
            .select("duration_min")
            .eq("user_id", user_id)
            .eq("log_date", today)
            .execute()
        )
        if result and result.data:
            return sum(r.get("duration_min", 0) for r in result.data)
    except Exception:
        pass
    return 0


def _record_focus_session(user_id: int, duration: int) -> dict:
    """Record a focus session and add points. Returns summary dict."""
    db = get_client()
    today = date.today().isoformat()

    # Try to log to focus_logs table; if table doesn't exist, skip gracefully
    try:
        db.table("focus_logs").insert({
            "user_id": user_id,
            "duration_min": duration,
            "log_date": today,
        }).execute()
    except Exception:
        pass  # Table may not exist yet; points still awarded

    # Calculate points
    base_points = 5
    daily_total = _get_daily_focus_minutes(user_id) + duration
    bonus = 10 if daily_total >= 120 else 0
    points_earned = base_points + bonus

    # Add points to user
    info = get_points_info(user_id)
    new_total = (info.get("points", 0) or 0) + points_earned
    db.table("users").update({"points": new_total}).eq("id", user_id).execute()

    return {
        "points_earned": points_earned,
        "total_points": new_total,
        "daily_total_min": daily_total,
        "bonus": bonus,
    }


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        reply = query.message.reply_text
    else:
        reply = update.message.reply_text

    await reply(
        "🔥 *深度工作打卡*\n\n"
        "完成了一段不被打断的专注工作？选择你的时长 👇\n\n"
        "每次打卡 +5 积分\n"
        "日累计超过 2 小时额外 +10 积分 💎",
        parse_mode="Markdown",
        reply_markup=_DURATION_KB,
    )
    return ASK_DURATION


async def receive_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data  # dw_dur_60
    try:
        duration = int(data.split("_")[-1])
    except ValueError:
        return ASK_DURATION

    user_id = update.effective_user.id
    result = _record_focus_session(user_id, duration)

    hours = result["daily_total_min"] // 60
    mins = result["daily_total_min"] % 60
    daily_str = f"{hours}小时{mins}分钟" if hours > 0 else f"{mins}分钟"

    bonus_line = ""
    if result["bonus"] > 0:
        bonus_line = "🎉 *日累计超2小时，额外 +10 积分！*\n\n"

    quote = _get_quote(user_id)

    await query.edit_message_text(
        f"✅ *深度工作打卡成功！*\n\n"
        f"⏱️ 本次时长：*{duration}分钟*\n"
        f"📊 今日累计：*{daily_str}*\n\n"
        f"{bonus_line}"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🪙 +{result['points_earned']} 积分（总计 {result['total_points']}）\n\n"
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
            CommandHandler("focus", entry),
            CallbackQueryHandler(entry, pattern="^feature_deep_work$"),
        ],
        states={
            ASK_DURATION: [CallbackQueryHandler(receive_duration, pattern="^dw_dur_")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_deep_work$"),
        ],
        conversation_timeout=120,
        per_user=True, per_chat=True, allow_reentry=True,
    )

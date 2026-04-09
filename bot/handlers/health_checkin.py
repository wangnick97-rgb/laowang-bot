"""
Feature: 健康打卡
每日健康状态记录：心情 → 一句话 → 完成
独立连续天数，积分与通用签到共用池。
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership
from db.health import do_health_checkin, get_health_leaderboard, get_gym_leaderboard, update_challenge_progress

ASK_MOOD, ASK_NOTE = range(2)

_MOOD_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("😤 挣扎中", callback_data="hmood_struggling"),
     InlineKeyboardButton("😐 还行", callback_data="hmood_okay")],
    [InlineKeyboardButton("😊 状态好", callback_data="hmood_good"),
     InlineKeyboardButton("🔥 火力全开", callback_data="hmood_fire")],
    [InlineKeyboardButton("❌ 取消", callback_data="cancel_health_ck")],
])

_MOOD_EMOJI = {
    "struggling": "😤",
    "okay": "😐",
    "good": "😊",
    "fire": "🔥",
}

_MOOD_NAME = {
    "struggling": "挣扎中",
    "okay": "还行",
    "good": "状态好",
    "fire": "火力全开",
}

_STREAK_MILESTONES = {
    3: ("🔥", "三天连续！习惯正在形成"),
    7: ("⭐", "一周达标！你已经超过了80%的人"),
    14: ("💫", "两周铁律！纪律正在变成本能"),
    30: ("💎", "一个月！你的身体已经开始感谢你"),
    60: ("👑", "两个月钢铁纪律！你就是标杆"),
    100: ("🐉", "传说级自律！这就是老王认可的水平"),
}

_WANG_HEALTH_QUOTES = [
    "身体是一切的底盘。底盘塌了，什么都白搭。",
    "自律不是苦行僧，是你选择对自己负责。",
    "打卡不是为了给别人看，是给自己一个交代。",
    "你的身体是你唯一不能换的资产。",
    "状态管理是创业者最被低估的能力。",
    "今天的坚持，是明天的底气。",
    "不要等身体出问题才开始重视它。预防永远比治疗便宜。",
]


def _get_quote(user_id: int) -> str:
    from datetime import date
    idx = (user_id + date.today().toordinal()) % len(_WANG_HEALTH_QUOTES)
    return _WANG_HEALTH_QUOTES[idx]


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_health_ck")]])


def _done_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏃 健身打卡", callback_data="feature_gym_log"),
         InlineKeyboardButton("📊 排行榜", callback_data="feature_health_rank")],
        [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
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
        "❤️ *健康打卡*\n\n"
        "今天整体状态怎么样？",
        parse_mode="Markdown",
        reply_markup=_MOOD_KB,
    )
    return ASK_MOOD


async def receive_mood(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data  # hmood_fire
    mood = data.replace("hmood_", "")
    if mood not in _MOOD_EMOJI:
        return ASK_MOOD

    context.user_data["health_mood"] = mood

    await query.edit_message_text(
        f"❤️ *健康打卡*\n\n"
        f"今日状态：{_MOOD_EMOJI[mood]} *{_MOOD_NAME[mood]}* ✅\n\n"
        f"用一句话记录今天的健康状态（可选）：\n"
        f"或者发送 `跳过` 直接完成打卡",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_NOTE


async def receive_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    note = "" if text in ("跳过", "skip", "略", "-") else text

    user_id = update.effective_user.id
    mood = context.user_data.get("health_mood", "okay")

    result = do_health_checkin(user_id, mood, note)

    if not result["success"]:
        await update.message.reply_text(
            "📌 *今天已经健康打卡过了！*\n\n"
            "明天继续保持 💪",
            parse_mode="Markdown",
            reply_markup=_done_kb(),
        )
        return ConversationHandler.END

    # 更新挑战进度
    try:
        update_challenge_progress(user_id, "health_checkin_days")
    except Exception:
        pass

    streak = result["streak"]
    emoji = _MOOD_EMOJI.get(mood, "😊")
    quote = _get_quote(user_id)

    # 连续天数里程碑
    milestone_text = ""
    if streak in _STREAK_MILESTONES:
        m_emoji, m_msg = _STREAK_MILESTONES[streak]
        milestone_text = f"\n\n🏅 *里程碑达成！* {m_emoji}\n_{m_msg}_"

    # 连续加成提示
    bonus_text = ""
    if result["streak_bonus"] > 0:
        bonus_text = f"（含连续加成 +{result['streak_bonus']}）"

    note_display = f"\n📝 {note}" if note else ""

    await update.message.reply_text(
        f"✅ *健康打卡成功！*\n\n"
        f"❤️ 状态：{emoji} {_MOOD_NAME.get(mood, mood)}{note_display}\n"
        f"📅 连续打卡：*{streak}* 天\n"
        f"🪙 +{result['points_earned']} 积分{bonus_text}（总计 {result['total_points']}）"
        f"{milestone_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ *老王说：{quote}*",
        parse_mode="Markdown",
        reply_markup=_done_kb(),
    )
    return ConversationHandler.END


# ── 健康排行榜 ────────────────────────────────────────────────────────────────

async def show_health_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    health_top = get_health_leaderboard(10)
    gym_top = get_gym_leaderboard(10)

    medals = ["🥇", "🥈", "🥉"]

    # 健康打卡连续天数榜
    lines = ["📊 *老王健康排行榜*\n\n❤️ *连续打卡榜*\n"]
    if health_top:
        for i, u in enumerate(health_top):
            medal = medals[i] if i < 3 else f"  {i+1}."
            name = u.get("full_name") or u.get("username") or str(u["id"])
            streak = u.get("health_streak", 0) or 0
            lines.append(f"{medal} {name} — {streak}天")
    else:
        lines.append("  暂无数据，快来打卡！")

    lines.append("\n🏋️ *健身次数榜*\n")
    if gym_top:
        for i, u in enumerate(gym_top):
            medal = medals[i] if i < 3 else f"  {i+1}."
            name = u.get("full_name") or u.get("username") or str(u["id"])
            count = u.get("gym_count", 0) or 0
            lines.append(f"{medal} {name} — {count}次")
    else:
        lines.append("  暂无数据，快来打卡！")

    lines.append("\n💡 坚持打卡，登上排行榜！")

    await query.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❤️ 健康打卡", callback_data="feature_health_checkin"),
             InlineKeyboardButton("🏃 健身打卡", callback_data="feature_gym_log")],
            [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
        ]),
    )


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
            CommandHandler("health", entry),
            CallbackQueryHandler(entry, pattern="^feature_health_checkin$"),
        ],
        states={
            ASK_MOOD: [CallbackQueryHandler(receive_mood, pattern="^hmood_")],
            ASK_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_note)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_health_ck$"),
        ],
        conversation_timeout=120,
        per_user=True, per_chat=True, allow_reentry=True,
    )

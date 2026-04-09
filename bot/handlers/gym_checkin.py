"""
Feature: 健身打卡
训练后记录：训练类型 → 时长 → 强度 → 完成
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership
from db.health import do_gym_log, update_challenge_progress

ASK_TYPE, ASK_DURATION, ASK_INTENSITY = range(3)

_TYPE_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🫸 推（胸/肩/三头）", callback_data="gym_push"),
     InlineKeyboardButton("🫷 拉（背/二头）", callback_data="gym_pull")],
    [InlineKeyboardButton("🦵 腿", callback_data="gym_legs"),
     InlineKeyboardButton("💪 全身", callback_data="gym_full")],
    [InlineKeyboardButton("🏃 有氧", callback_data="gym_cardio"),
     InlineKeyboardButton("🧘 休息日活动", callback_data="gym_rest")],
    [InlineKeyboardButton("❌ 取消", callback_data="cancel_gym")],
])

_DURATION_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("30min", callback_data="gym_dur_30"),
     InlineKeyboardButton("45min", callback_data="gym_dur_45"),
     InlineKeyboardButton("60min", callback_data="gym_dur_60")],
    [InlineKeyboardButton("75min", callback_data="gym_dur_75"),
     InlineKeyboardButton("90min", callback_data="gym_dur_90"),
     InlineKeyboardButton("120min", callback_data="gym_dur_120")],
    [InlineKeyboardButton("❌ 取消", callback_data="cancel_gym")],
])

_INTENSITY_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("1⭐ 轻松", callback_data="gym_int_1"),
     InlineKeyboardButton("2⭐ 适中", callback_data="gym_int_2"),
     InlineKeyboardButton("3⭐ 正常", callback_data="gym_int_3")],
    [InlineKeyboardButton("4⭐ 刻苦", callback_data="gym_int_4"),
     InlineKeyboardButton("5⭐ 极限", callback_data="gym_int_5")],
    [InlineKeyboardButton("❌ 取消", callback_data="cancel_gym")],
])

_TYPE_NAMES = {
    "gym_push": ("push", "推日（胸/肩/三头）"),
    "gym_pull": ("pull", "拉日（背/二头）"),
    "gym_legs": ("legs", "腿日"),
    "gym_full": ("full", "全身训练"),
    "gym_cardio": ("cardio", "有氧训练"),
    "gym_rest": ("rest", "休息日活动"),
}

_INTENSITY_EMOJI = {1: "😌", 2: "💪", 3: "🔥", 4: "😤", 5: "🤯"}

_WANG_QUOTES = [
    "练了就是赢了。大部分人今天连健身房的门都没摸到。",
    "肌肉不会辜负任何一次训练。",
    "真正的强者不是练得最猛的，是最持续的。",
    "你现在流的每一滴汗，都在给未来的自己投票。",
    "别人在刷手机的时候，你在刷PR。这就是差距。",
    "推完这组，你比昨天的自己更强了一点。",
    "腿日最痛苦，但腿日决定你的睾酮水平。别跳腿日。",
]


def _get_quote(user_id: int) -> str:
    from datetime import date
    idx = (user_id + date.today().toordinal()) % len(_WANG_QUOTES)
    return _WANG_QUOTES[idx]


def _done_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 排行榜", callback_data="feature_health_rank"),
         InlineKeyboardButton("❤️ 健康打卡", callback_data="feature_health_checkin")],
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
        "🏃 *健身打卡*\n\n"
        "今天练了什么？选择训练类型 👇",
        parse_mode="Markdown",
        reply_markup=_TYPE_KB,
    )
    return ASK_TYPE


async def receive_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data
    if data not in _TYPE_NAMES:
        return ASK_TYPE

    key, name = _TYPE_NAMES[data]
    context.user_data["gym_type"] = key
    context.user_data["gym_type_name"] = name

    await query.edit_message_text(
        f"🏃 *健身打卡*\n\n"
        f"训练类型：*{name}* ✅\n\n"
        f"训练时长是多久？",
        parse_mode="Markdown",
        reply_markup=_DURATION_KB,
    )
    return ASK_DURATION


async def receive_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data  # gym_dur_60
    try:
        duration = int(data.split("_")[-1])
    except ValueError:
        return ASK_DURATION

    context.user_data["gym_duration"] = duration

    await query.edit_message_text(
        f"🏃 *健身打卡*\n\n"
        f"训练类型：*{context.user_data.get('gym_type_name')}*\n"
        f"训练时长：*{duration}分钟* ✅\n\n"
        f"训练强度怎么样？",
        parse_mode="Markdown",
        reply_markup=_INTENSITY_KB,
    )
    return ASK_INTENSITY


async def receive_intensity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data  # gym_int_4
    try:
        intensity = int(data.split("_")[-1])
    except ValueError:
        return ASK_INTENSITY

    user_id = update.effective_user.id
    workout_type = context.user_data.get("gym_type", "full")
    duration = context.user_data.get("gym_duration", 60)
    type_name = context.user_data.get("gym_type_name", "训练")

    result = do_gym_log(user_id, workout_type, duration, intensity)

    if not result["success"]:
        await query.edit_message_text(
            "📌 *今天已经打过健身卡了！*\n\n"
            "明天继续加油 💪",
            parse_mode="Markdown",
            reply_markup=_done_kb(),
        )
        return ConversationHandler.END

    # 更新挑战进度
    try:
        update_challenge_progress(user_id, "workout_count")
    except Exception:
        pass

    emoji = _INTENSITY_EMOJI.get(intensity, "💪")
    quote = _get_quote(user_id)

    await query.edit_message_text(
        f"✅ *健身打卡成功！*\n\n"
        f"🏋️ 训练类型：{type_name}\n"
        f"⏱️ 训练时长：{duration}分钟\n"
        f"💥 训练强度：{'⭐' * intensity} {emoji}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🪙 +{result['points_earned']} 积分（总计 {result['total_points']}）\n"
        f"🏋️ 累计训练 *{result['gym_count']}* 次\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
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
            CommandHandler("gym", entry),
            CallbackQueryHandler(entry, pattern="^feature_gym_log$"),
        ],
        states={
            ASK_TYPE: [CallbackQueryHandler(receive_type, pattern="^gym_(push|pull|legs|full|cardio|rest)$")],
            ASK_DURATION: [CallbackQueryHandler(receive_duration, pattern="^gym_dur_")],
            ASK_INTENSITY: [CallbackQueryHandler(receive_intensity, pattern="^gym_int_")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_gym$"),
        ],
        conversation_timeout=120,
        per_user=True, per_chat=True, allow_reentry=True,
    )

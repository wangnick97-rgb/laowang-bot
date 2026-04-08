"""
Feature: 每日成长打卡 + 积分 + 宝箱 + 成就 + 金句
签到 → 积分+宝箱+金句 → 反思题 → Claude 回应
"""
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership, require_usage_quota
from services.claude_client import call_claude
from db.points import (
    do_checkin, get_points_info, get_leaderboard,
    open_chest, unlock_special_badge, ACHIEVEMENTS,
)

ASK_REFLECTION = 0
_KEY = "daily_checkin"

_QUESTIONS = [
    "今天你做的哪件事让你感到最「真实的自己」？",
    "如果今天的你回到一年前，你会给当时的自己什么建议？",
    "今天你有没有做了一件本可以不做但你选择做了的事？为什么？",
    "今天最让你消耗能量的一件事是什么？你能减少这类消耗吗？",
    "今天你在哪件事上妥协了？你接受这个妥协吗？",
    "如果今天只能保留一件事，你会保留什么？",
    "今天你有没有在意别人的眼光而做了什么或没做什么？",
]

# 老王每日金句（签到后才能看到）
_DAILY_QUOTES = [
    "普通人最大的优势就是没人关注你，你可以安静地试错。",
    "不要用战术的勤奋掩盖战略的懒惰。",
    "真正的自由不是想做什么就做什么，而是不想做什么就可以不做什么。",
    "赚钱的本质是提供价值，不是消耗时间。",
    "在没有方向的时候，提升认知就是最好的方向。",
    "大部分人高估了一年能做的事，低估了五年能做的事。",
    "最贵的成本是机会成本——你选择做这件事，就放弃了做其他事。",
    "不要问「能不能做」，要问「值不值得做」。",
    "情绪是信号，不是决策依据。记录它，但别跟着它走。",
    "复利不只是金融概念，知识、技能、人脉都有复利。",
    "好的交易系统不会让你暴富，但会让你不暴亏。",
    "内容创业最大的误区：以为数量能弥补质量。",
    "真正的壁垒不是你会什么，而是你愿意持续做别人不愿意做的事。",
    "你今天的选择，决定了三年后的你。",
    "Airbnb 赚的不是房租差价，赚的是运营效率差。",
    "不要等准备好了再开始，开始了才知道需要准备什么。",
    "真正的高手，是把一件事做到极致，而不是什么都会一点。",
    "停止焦虑最好的方式：此刻就去做那件让你焦虑的事。",
    "社交媒体上的「成功」都是结果，别模仿结果，要模仿过程。",
    "投资最重要的不是选对，而是错的时候亏得少。",
    "90%的商业问题，本质都是定位问题。",
    "每天进步1%，一年后你会变成现在的37倍。这不是鸡汤，是数学。",
    "别人的建议听三分就够了，剩下七分要靠自己踩坑。",
    "执行力才是最稀缺的资源。想法一文不值，做到了才值钱。",
    "管理好你的注意力，比管理好你的钱更重要。",
    "创业第一件事不是找钱，是找到一个愿意付钱的人。",
    "最好的学习方式：带着问题去学，学完马上去用。",
    "所有的成长都发生在舒适区之外。不舒服，说明你在进步。",
    "时间是最公平的资源。你把时间花在哪，成就就在哪。",
    "别小看小事的积累。每一次签到，都是你对自己的一次承诺。",
]

_STREAK_EMOJIS = {3: "🔥", 7: "⭐", 14: "💎", 30: "👑", 60: "🏆", 100: "🐉"}


def _get_question(user_id: int) -> str:
    idx = (user_id + date.today().toordinal()) % len(_QUESTIONS)
    return _QUESTIONS[idx]


def _get_daily_quote() -> str:
    idx = date.today().toordinal() % len(_DAILY_QUOTES)
    return _DAILY_QUOTES[idx]


def _streak_badge(streak: int) -> str:
    badge = ""
    for threshold, emoji in sorted(_STREAK_EMOJIS.items()):
        if streak >= threshold:
            badge = emoji
    return badge


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_checkin")]])

def _done_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🏆 排行榜", callback_data="checkin_leaderboard"),
        InlineKeyboardButton("🎖️ 我的成就", callback_data="my_badges"),
    ], [
        InlineKeyboardButton("← 主菜单", callback_data="menu_main"),
    ]])


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    reply = query.message.reply_text if query else update.message.reply_text
    if query:
        await query.answer()

    user_id = update.effective_user.id
    result = do_checkin(user_id)
    question = _get_question(user_id)
    quote = _get_daily_quote()

    if result["success"]:
        streak = result["streak"]
        badge = _streak_badge(streak)
        streak_text = f"连续签到 *{streak}* 天 {badge}" if badge else f"连续签到 *{streak}* 天"

        # 保护卡提示
        shield_text = ""
        if result.get("shield_used"):
            shield_text = "\n🛡️ *保护卡已自动使用！* 连续签到未中断"

        # 成就解锁提示
        badge_text = ""
        new_badges = result.get("new_badges", [])
        if new_badges:
            unlocked = [f"{ACHIEVEMENTS[b]['emoji']} *{ACHIEVEMENTS[b]['name']}*" for b in new_badges if b in ACHIEVEMENTS]
            badge_text = "\n\n🎖️ 解锁新成就：" + " ".join(unlocked)

        # 开宝箱
        chest = open_chest(user_id)
        if chest["name"] == "传说宝箱":
            unlock_special_badge(user_id, "chest_dragon")

        chest_text = f"\n🎁 宝箱开启：{chest['emoji']} *{chest['name']}*"
        if chest["is_shield"]:
            chest_text += " — 获得 1 张签到保护卡！"
        else:
            chest_text += f" — +{chest['points']} 积分！"

        # 更新总积分（宝箱积分已在 open_chest 中加过）
        info = get_points_info(user_id)
        total = info.get("points", 0)

        await reply(
            f"✅ *签到成功！*\n\n"
            f"🪙 +{result['points_earned']} 积分（总计 {total}）\n"
            f"📅 {streak_text}{shield_text}\n"
            f"{chest_text}{badge_text}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💬 *老王今日金句*\n"
            f"_{quote}_\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🌱 *今日反思题*\n\n"
            f"*{question}*\n\n"
            f"写下你的想法，我会认真回应 👇",
            parse_mode="Markdown",
            reply_markup=_cancel_kb(),
        )
    else:
        info = get_points_info(user_id)
        await reply(
            f"📌 *今天已经签到过了*\n\n"
            f"🪙 当前积分：{info.get('points', 0)}\n"
            f"📅 连续签到：{info.get('checkin_streak', 0)} 天\n\n"
            f"💬 *老王今日金句*\n"
            f"_{quote}_\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"不过你仍然可以回答今天的反思题：\n\n"
            f"*{question}*\n\n"
            f"👇 写下你的想法",
            parse_mode="Markdown",
            reply_markup=_cancel_kb(),
        )
    return ASK_REFLECTION


@require_usage_quota
async def respond(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    question = _get_question(user_id)
    user_input = f"今天的打卡题：{question}\n\n我的回答：{update.message.text.strip()}"

    await update.message.reply_text("🌱 正在回应你的打卡...")
    result = await call_claude(_KEY, user_input, user_id=user_id, max_tokens=600)
    await update.message.reply_text(result, parse_mode="Markdown", reply_markup=_done_kb())
    return ConversationHandler.END


async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    top = get_leaderboard(10)
    if not top:
        await query.message.reply_text("暂无排行数据，快去签到吧！")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 *积分排行榜 TOP 10*\n"]
    for i, u in enumerate(top):
        medal = medals[i] if i < 3 else f"  {i+1}."
        name = u.get("full_name") or u.get("username") or str(u["id"])
        streak = u.get("checkin_streak", 0) or 0
        badge = _streak_badge(streak)
        lines.append(f"{medal} {name} — {u.get('points', 0)} 分 | {streak}天{badge}")

    lines.append(f"\n💡 连续签到可获得额外积分加成")
    await query.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌱 去签到", callback_data="feature_checkin"),
             InlineKeyboardButton("← 主菜单", callback_data="menu_main")],
        ]),
    )


async def show_badges(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    info = get_points_info(update.effective_user.id)
    user_badges = info.get("badges") or []

    lines = ["🎖️ *我的成就墙*\n"]
    for badge_id, badge_info in ACHIEVEMENTS.items():
        if badge_id in user_badges:
            lines.append(f"  {badge_info['emoji']} *{badge_info['name']}* — {badge_info['desc']}")
        else:
            lines.append(f"  🔒 ??? — {badge_info['desc']}")

    unlocked = len(user_badges)
    total = len(ACHIEVEMENTS)
    lines.insert(1, f"已解锁 {unlocked}/{total}\n")

    shields = info.get("streak_shields", 0) or 0
    lines.append(f"\n🛡️ 签到保护卡：{shields} 张")

    await query.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌱 去签到", callback_data="feature_checkin"),
             InlineKeyboardButton("← 主菜单", callback_data="menu_main")],
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
            CommandHandler("checkin", entry),
            CallbackQueryHandler(entry, pattern="^feature_checkin$"),
        ],
        states={ASK_REFLECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, respond)]},
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_checkin$"),
        ],
        conversation_timeout=300,
        per_user=True, per_chat=True, allow_reentry=True,
    )

"""
积分查询 + 积分商城
/points — 查看积分、连续签到、可兑换奖励
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.middleware import require_membership
from db.points import get_points_info, redeem_points, get_leaderboard
from db.users import get_user, set_membership

# 积分商城
REWARDS = [
    {"id": "shield_1", "name": "🛡️ 签到保护卡 ×1", "cost": 80, "desc": "断签时自动保护连续天数"},
    {"id": "extra_5", "name": "📱 额外 5 次/天 使用额度", "cost": 100, "desc": "当日使用上限 +5"},
    {"id": "member_7", "name": "💎 会员延期 7 天", "cost": 500, "desc": "会员有效期延长 7 天"},
    {"id": "consult_discount", "name": "🎯 咨询 9 折券", "cost": 800, "desc": "1v1 咨询享 9 折优惠"},
    # 健康专区
    {"id": "health_shield", "name": "❤️ 健康打卡保护卡 ×1", "cost": 80, "desc": "健康断签时保护连续天数"},
    {"id": "ai_meal_7", "name": "🍽️ AI食谱定制(7天)", "cost": 200, "desc": "解锁7天AI专属食谱"},
    {"id": "ai_workout_4w", "name": "🏋️ AI训练计划(4周)", "cost": 300, "desc": "解锁4周AI定制训练"},
]


@require_membership
async def cmd_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    info = get_points_info(user_id)
    points = info.get("points", 0) or 0
    streak = info.get("checkin_streak", 0) or 0

    # 积分商城列表
    shop_lines = []
    for r in REWARDS:
        status = "✅" if points >= r["cost"] else "🔒"
        shop_lines.append(f"{status} {r['name']} — {r['cost']} 积分")

    text = (
        f"🪙 *我的积分*\n\n"
        f"当前积分：*{points}*\n"
        f"连续签到：*{streak}* 天\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🛍️ *积分商城*\n\n"
        + "\n".join(shop_lines) +
        f"\n\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 每日签到得 10+ 积分，连续签到额外加成"
    )

    buttons = []
    for r in REWARDS:
        if points >= r["cost"]:
            buttons.append([InlineKeyboardButton(
                f"兑换：{r['name']}",
                callback_data=f"redeem_{r['id']}",
            )])

    buttons.append([
        InlineKeyboardButton("🌱 去签到", callback_data="feature_checkin"),
        InlineKeyboardButton("🏆 排行榜", callback_data="checkin_leaderboard"),
    ])

    reply = query.message.reply_text if query else update.message.reply_text
    await reply(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def callback_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    reward_id = query.data.replace("redeem_", "")
    reward = next((r for r in REWARDS if r["id"] == reward_id), None)
    if not reward:
        return

    user_id = update.effective_user.id
    success = redeem_points(user_id, reward["cost"], reward["name"])

    if success:
        # 处理具体奖励逻辑
        if reward_id == "shield_1":
            from db.client import get_client as _gc
            _info = get_points_info(user_id)
            _gc().table("users").update({
                "streak_shields": (_info.get("streak_shields", 0) or 0) + 1,
            }).eq("id", user_id).execute()
        elif reward_id == "member_7":
            _extend_membership(user_id, 7)

        info = get_points_info(user_id)
        await query.edit_message_text(
            f"✅ *兑换成功！*\n\n"
            f"🎁 {reward['name']}\n"
            f"📌 {reward['desc']}\n\n"
            f"🪙 剩余积分：{info.get('points', 0)}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("← 主菜单", callback_data="menu_main")],
            ]),
        )
    else:
        await query.edit_message_text(
            f"❌ 积分不足，无法兑换 {reward['name']}（需要 {reward['cost']} 积分）",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌱 去签到赚积分", callback_data="feature_checkin")],
            ]),
        )


def _extend_membership(user_id: int, days: int):
    from datetime import datetime, timedelta, timezone
    from db.client import get_client
    db = get_client()
    user = get_user(user_id)
    now = datetime.now(timezone.utc)
    current = user.get("membership_expires_at")
    if current:
        base = datetime.fromisoformat(current.replace("Z", "+00:00"))
        if base < now:
            base = now
    else:
        base = now
    new_expires = (base + timedelta(days=days)).isoformat()
    db.table("users").update({"membership_expires_at": new_expires}).eq("id", user_id).execute()

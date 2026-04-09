"""
积分商城 — 按会员等级分层
免费用户：实用好物 / 会员：高端数码 / 私董会：顶级权益
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.points import get_points_info, redeem_points, get_leaderboard
from db.users import get_user

# ── 分层商品 ──────────────────────────────────────────────────────────────────

# 所有人可见可兑
REWARDS_ALL = [
    {"id": "shield_1", "name": "🛡️ 签到保护卡 ×1", "cost": 80, "desc": "断签时自动保护连续天数", "tier": "all"},
    {"id": "health_shield", "name": "❤️ 健康保护卡 ×1", "cost": 80, "desc": "健康断签时保护连续天数", "tier": "all"},
    {"id": "extra_5", "name": "📱 额外5次/天使用额度", "cost": 100, "desc": "当日AI使用上限+5", "tier": "all"},
]

# 免费用户专区 — 吸引持续签到
REWARDS_FREE = [
    {"id": "book_1", "name": "📚 老王推荐书单(电子版)", "cost": 200, "desc": "老王精选10本必读书PDF", "tier": "free"},
    {"id": "template_1", "name": "📋 商业计划书模板", "cost": 300, "desc": "老王亲用的BP模板", "tier": "free"},
    {"id": "checklist_1", "name": "✅ 创业检查清单", "cost": 150, "desc": "从0到1创业50项checklist", "tier": "free"},
    {"id": "wallpaper_1", "name": "🖼️ 老王自律壁纸包", "cost": 100, "desc": "12张高清手机壁纸", "tier": "free"},
    {"id": "member_7", "name": "💎 会员体验7天", "cost": 500, "desc": "免费体验全部会员功能", "tier": "free"},
    {"id": "earphone_1", "name": "🎧 蓝牙运动耳机", "cost": 2000, "desc": "实物奖品 (包邮)", "tier": "free"},
    {"id": "kindle_1", "name": "📖 Kindle Paperwhite", "cost": 5000, "desc": "实物奖品 (包邮)", "tier": "free"},
    {"id": "keyboard_1", "name": "⌨️ 机械键盘", "cost": 3000, "desc": "实物奖品 (包邮)", "tier": "free"},
]

# 会员专区 — 高端数码
REWARDS_MEMBER = [
    {"id": "member_30", "name": "💎 会员延期30天", "cost": 500, "desc": "会员有效期+30天", "tier": "member"},
    {"id": "consult_15", "name": "🎯 15分钟快速咨询", "cost": 800, "desc": "老王1v1语音15min", "tier": "member"},
    {"id": "consult_discount", "name": "🎯 咨询9折券", "cost": 600, "desc": "1v1咨询享9折", "tier": "member"},
    {"id": "airpods_1", "name": "🎧 AirPods Pro", "cost": 8000, "desc": "实物奖品 (包邮)", "tier": "member"},
    {"id": "ipad_1", "name": "📱 iPad Air", "cost": 15000, "desc": "实物奖品 (包邮)", "tier": "member"},
    {"id": "iphone_1", "name": "📱 iPhone 16", "cost": 25000, "desc": "实物奖品 (包邮)", "tier": "member"},
    {"id": "macbook_1", "name": "💻 MacBook Air M3", "cost": 40000, "desc": "实物奖品 (包邮)", "tier": "member"},
]

# 私董会专区 — 顶级权益
REWARDS_VIP = [
    {"id": "claude_3m", "name": "🤖 Claude Pro 3个月", "cost": 5000, "desc": "价值$60的Claude会员", "tier": "vip"},
    {"id": "chatgpt_3m", "name": "🤖 ChatGPT Plus 3个月", "cost": 5000, "desc": "价值$60的GPT会员", "tier": "vip"},
    {"id": "vip_extend_30", "name": "👑 私董会延期30天", "cost": 3000, "desc": "私董会有效期+30天", "tier": "vip"},
    {"id": "offline_meet", "name": "🤝 老王线下交流会名额", "cost": 15000, "desc": "限定城市线下见面会1位", "tier": "vip"},
    {"id": "cash_100", "name": "💵 现金$100", "cost": 20000, "desc": "直接提现到支付宝/微信", "tier": "vip"},
    {"id": "cash_500", "name": "💵 现金$500", "cost": 80000, "desc": "直接提现到支付宝/微信", "tier": "vip"},
    {"id": "dinner_wang", "name": "🍽️ 和老王吃饭", "cost": 50000, "desc": "老王请你吃饭+2小时深度交流", "tier": "vip"},
    {"id": "mentorship_1m", "name": "🧠 老王1个月导师计划", "cost": 100000, "desc": "每周1次30min通话+随时微信答疑", "tier": "vip"},
]

# 合并用于兑换查找
ALL_REWARDS = REWARDS_ALL + REWARDS_FREE + REWARDS_MEMBER + REWARDS_VIP


def _get_tier(user_id: int) -> str:
    user = get_user(user_id)
    if not user:
        return "free"
    if user.get("membership_status") == "admin":
        return "admin"
    return user.get("membership_tier", "free")


async def cmd_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    info = get_points_info(user_id)
    points = info.get("points", 0) or 0
    streak = info.get("checkin_streak", 0) or 0
    tier = _get_tier(user_id)

    # 构建商品列表
    def fmt_section(title, rewards):
        lines = [f"\n{title}\n"]
        for r in rewards:
            status = "✅" if points >= r["cost"] else "🔒"
            lines.append(f"  {status} {r['name']} — {r['cost']}分")
        return "\n".join(lines)

    sections = fmt_section("🔧 *通用道具*", REWARDS_ALL)

    if tier in ("free",):
        sections += fmt_section("\n🎁 *好物兑换*", REWARDS_FREE)
        sections += "\n\n🔒 _开通会员解锁 MacBook / iPhone 等高端奖品_"
        sections += "\n🔒 _开通私董会解锁 现金提现 / 线下交流 等顶级权益_"
    elif tier in ("member",):
        sections += fmt_section("\n🎁 *好物兑换*", REWARDS_FREE)
        sections += fmt_section("\n💎 *会员专区*", REWARDS_MEMBER)
        sections += "\n\n🔒 _升级私董会解锁 现金提现 / 老王线下 等顶级权益_"
    elif tier in ("vip", "admin"):
        sections += fmt_section("\n🎁 *好物兑换*", REWARDS_FREE)
        sections += fmt_section("\n💎 *会员专区*", REWARDS_MEMBER)
        sections += fmt_section("\n👑 *私董会专区*", REWARDS_VIP)

    text = (
        f"🪙 *我的积分*\n\n"
        f"当前积分：*{points}*\n"
        f"连续签到：*{streak}* 天\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛍️ *积分商城*"
        f"{sections}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 每日签到+打卡+完成挑战赚积分"
    )

    # 兑换按钮（只显示买得起的，最多6个）
    buttons = []
    eligible = [r for r in ALL_REWARDS if points >= r["cost"] and _can_access(tier, r["tier"])]
    for r in eligible[:6]:
        buttons.append([InlineKeyboardButton(
            f"兑换：{r['name']} ({r['cost']}分)",
            callback_data=f"redeem_{r['id']}",
        )])

    buttons.append([
        InlineKeyboardButton("✅ 去签到", callback_data="feature_checkin"),
        InlineKeyboardButton("🏆 排行榜", callback_data="checkin_leaderboard"),
    ])
    buttons.append([InlineKeyboardButton("← 返回会员中心", callback_data="menu_member")])

    reply = query.message.reply_text if query else update.message.reply_text
    await reply(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


def _can_access(user_tier: str, reward_tier: str) -> bool:
    """检查用户tier是否能兑换该奖品。"""
    if reward_tier == "all":
        return True
    if user_tier in ("admin",):
        return True
    tier_levels = {"free": 0, "member": 1, "vip": 2}
    return tier_levels.get(user_tier, 0) >= tier_levels.get(reward_tier, 0)


async def callback_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    reward_id = query.data.replace("redeem_", "")
    reward = next((r for r in ALL_REWARDS if r["id"] == reward_id), None)
    if not reward:
        return

    user_id = update.effective_user.id
    tier = _get_tier(user_id)

    # 检查tier权限
    if not _can_access(tier, reward["tier"]):
        await query.edit_message_text(
            f"🔒 此奖品需要更高会员等级才能兑换",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 升级会员", callback_data="join_member")],
            ]),
        )
        return

    success = redeem_points(user_id, reward["cost"], reward["name"])

    if success:
        # 处理具体奖励逻辑
        if reward_id == "shield_1" or reward_id == "health_shield":
            from db.client import get_client as _gc
            _info = get_points_info(user_id)
            _gc().table("users").update({
                "streak_shields": (_info.get("streak_shields", 0) or 0) + 1,
            }).eq("id", user_id).execute()
        elif reward_id == "member_7":
            _extend_membership(user_id, 7)
        elif reward_id == "member_30":
            _extend_membership(user_id, 30)
        elif reward_id == "vip_extend_30":
            _extend_membership(user_id, 30)

        # 实物/高价值奖品需要通知管理员
        needs_admin = reward["cost"] >= 2000
        if needs_admin:
            from db.users import get_admin_ids
            name = update.effective_user.full_name or update.effective_user.username or str(user_id)
            for admin_id in get_admin_ids():
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=(
                            f"🎁 *积分兑换通知*\n\n"
                            f"用户: {name} (`{user_id}`)\n"
                            f"兑换: {reward['name']}\n"
                            f"消耗: {reward['cost']}积分\n\n"
                            f"⚠️ 需要人工处理发货/安排"
                        ),
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

        info = get_points_info(user_id)
        admin_note = "\n\n📮 *管理员已收到通知，会尽快处理*" if needs_admin else ""
        await query.edit_message_text(
            f"✅ *兑换成功！*\n\n"
            f"🎁 {reward['name']}\n"
            f"📌 {reward['desc']}\n\n"
            f"🪙 剩余积分：{info.get('points', 0)}"
            f"{admin_note}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("← 返回会员中心", callback_data="menu_member")],
            ]),
        )
    else:
        await query.edit_message_text(
            f"❌ 积分不足，无法兑换 {reward['name']}（需要 {reward['cost']} 积分）",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ 去签到赚积分", callback_data="feature_checkin")],
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

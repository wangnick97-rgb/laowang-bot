"""
邀请机制：用户分享邀请链接，新用户通过链接注册后，双方获得积分奖励。
- 积分奖励按双方tier分级：免费/会员/私董会
- 会员邀请人额外获得 7 天会员延期

Bot deep link: https://t.me/BOT_USERNAME?start=ref_<user_id>
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.users import get_user, is_member, get_admin_ids
from db.client import get_client

logger = logging.getLogger(__name__)

REFERRAL_REWARD_DAYS = 7

# 邀请积分奖励（按邀请人tier）
# {inviter_tier: (inviter_points, invitee_points)}
REFERRAL_POINTS = {
    "free":   (10,  10),    # 免费用户邀请：双方各10
    "member": (100, 80),    # 会员邀请：邀请人100，新人80
    "vip":    (200, 150),   # 私董会邀请：邀请人200，新人150
    "admin":  (200, 150),
}


def _get_tier(user: dict) -> str:
    """获取用户tier。"""
    if not user:
        return "free"
    status = user.get("membership_status", "free")
    if status == "admin":
        return "admin"
    tier = user.get("membership_tier", "free")
    return tier if tier in REFERRAL_POINTS else "free"


async def cmd_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a personal invite link for the user — all users can invite."""
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    user = get_user(user_id)

    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    tier = _get_tier(user)
    inviter_pts, invitee_pts = REFERRAL_POINTS.get(tier, REFERRAL_POINTS["free"])

    # 统计历史邀请数
    db = get_client()
    ref_count = db.table("referrals").select("id", count="exact").eq("referrer_id", user_id).execute()
    total_invited = ref_count.count or 0

    tier_label = {"free": "🆓 免费用户", "member": "💎 会员", "vip": "👑 私董会", "admin": "👑 管理员"}.get(tier, "🆓 免费用户")

    reply = query.message.reply_text if query else update.message.reply_text
    await reply(
        f"🎁 *你的专属邀请链接*\n\n"
        f"`{link}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 你的身份: {tier_label}\n"
        f"👥 已邀请: *{total_invited}* 人\n\n"
        f"*邀请奖励:*\n"
        f"• 你获得 *{inviter_pts}* 积分\n"
        f"• 朋友获得 *{invitee_pts}* 积分\n"
        + (f"• 额外 *{REFERRAL_REWARD_DAYS} 天*会员延期\n" if tier in ("member", "vip", "admin") else "")
        + f"\n"
        f"💡 *升级会员，邀请奖励更多！*\n"
        f"  免费: 双方各10分\n"
        f"  会员: 邀请人100 + 新人80\n"
        f"  私董会: 邀请人200 + 新人150\n\n"
        f"长按链接复制即可 👆",
        parse_mode="Markdown",
    )


async def process_referral(context: ContextTypes.DEFAULT_TYPE, new_user_id: int, referrer_id: int):
    """Called when a new user joins via referral link. Rewards both parties with points."""
    referrer = get_user(referrer_id)
    if not referrer:
        return

    db = get_client()
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)

    # 防重复：检查是否已记录过
    existing = db.table("referrals").select("id").eq("referrer_id", referrer_id).eq("invitee_id", new_user_id).maybe_single().execute()
    if existing and existing.data:
        return

    # 计算积分
    tier = _get_tier(referrer)
    inviter_pts, invitee_pts = REFERRAL_POINTS.get(tier, REFERRAL_POINTS["free"])

    # 记录邀请关系
    db.table("referrals").insert({
        "referrer_id": referrer_id,
        "invitee_id": new_user_id,
        "referrer_tier": tier,
        "inviter_points": inviter_pts,
        "invitee_points": invitee_pts,
    }).execute()

    # 给邀请人加积分
    referrer_info = db.table("users").select("points").eq("id", referrer_id).maybe_single().execute()
    referrer_current = (referrer_info.data or {}).get("points", 0) or 0
    db.table("users").update({"points": referrer_current + inviter_pts}).eq("id", referrer_id).execute()

    # 给新用户加积分
    invitee_info = db.table("users").select("points").eq("id", new_user_id).maybe_single().execute()
    invitee_current = (invitee_info.data or {}).get("points", 0) or 0
    db.table("users").update({"points": invitee_current + invitee_pts}).eq("id", new_user_id).execute()

    # 会员/VIP邀请人额外延长会员天数
    if is_member(referrer):
        current_expires = referrer.get("membership_expires_at")
        if current_expires:
            base = datetime.fromisoformat(current_expires.replace("Z", "+00:00"))
            if base < now:
                base = now
            new_expires = (base + timedelta(days=REFERRAL_REWARD_DAYS)).isoformat()
            db.table("users").update(
                {"membership_expires_at": new_expires}
            ).eq("id", referrer_id).execute()

    # 通知邀请人
    try:
        new_user = get_user(new_user_id)
        new_name = new_user.get("full_name") or new_user.get("username") or str(new_user_id) if new_user else str(new_user_id)
        msg = (
            f"🎉 *邀请成功！*\n\n"
            f"你邀请的 *{new_name}* 已注册！\n\n"
            f"*奖励已到账:*\n"
            f"• 你获得 +{inviter_pts} 积分 🪙\n"
            f"• {new_name} 获得 +{invitee_pts} 积分 🪙"
        )
        if is_member(referrer):
            msg += f"\n• 会员延期 {REFERRAL_REWARD_DAYS} 天 ✅"
        await context.bot.send_message(
            chat_id=referrer_id, text=msg, parse_mode="Markdown",
        )
    except Exception:
        logger.warning("Failed to notify referrer %s", referrer_id)

    # 通知新用户
    try:
        referrer_name = referrer.get("full_name") or referrer.get("username") or str(referrer_id)
        await context.bot.send_message(
            chat_id=new_user_id,
            text=(
                f"🎁 *欢迎奖励！*\n\n"
                f"你通过 *{referrer_name}* 的邀请加入，获得 *{invitee_pts}* 积分！🪙\n\n"
                f"发送 /checkin 每日签到继续赚积分"
            ),
            parse_mode="Markdown",
        )
    except Exception:
        pass

    # 通知管理员
    for admin_id in get_admin_ids():
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🔗 *邀请记录*\n"
                    f"邀请人: `{referrer_id}` ({tier})\n"
                    f"新用户: `{new_user_id}`\n"
                    f"积分: 邀请人+{inviter_pts} / 新人+{invitee_pts}"
                ),
                parse_mode="Markdown",
            )
        except Exception:
            pass

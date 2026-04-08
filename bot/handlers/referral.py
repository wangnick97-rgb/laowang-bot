"""
邀请机制：老会员分享邀请链接，新用户通过链接注册后，双方获得奖励。
- 邀请人：延长会员 7 天
- 被邀请人：注册后自动标记来源

Bot deep link: https://t.me/BOT_USERNAME?start=ref_<user_id>
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.users import get_user, is_member, get_admin_ids
from db.client import get_client

logger = logging.getLogger(__name__)

REFERRAL_REWARD_DAYS = 7


async def cmd_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a personal invite link for the user."""
    user = get_user(update.effective_user.id)
    if not user or not is_member(user):
        await update.message.reply_text("此功能仅限会员使用。发送 /start 了解如何开通。")
        return

    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{update.effective_user.id}"

    await update.message.reply_text(
        f"🎁 *你的专属邀请链接*\n\n"
        f"`{link}`\n\n"
        f"分享给朋友，对方通过链接注册后：\n"
        f"• 你获得 *{REFERRAL_REWARD_DAYS} 天*会员延期\n"
        f"• 朋友可以直接体验工具\n\n"
        f"长按链接复制即可 👆",
        parse_mode="Markdown",
    )


async def process_referral(context: ContextTypes.DEFAULT_TYPE, new_user_id: int, referrer_id: int):
    """Called when a new user joins via referral link. Rewards the referrer."""
    referrer = get_user(referrer_id)
    if not referrer or not is_member(referrer):
        return

    # Extend referrer's membership
    db = get_client()
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    current_expires = referrer.get("membership_expires_at")

    if current_expires:
        base = datetime.fromisoformat(current_expires.replace("Z", "+00:00"))
        if base < now:
            base = now
    else:
        # No expiry = permanent member, give them a note instead
        base = None

    if base:
        new_expires = (base + timedelta(days=REFERRAL_REWARD_DAYS)).isoformat()
        db.table("users").update(
            {"membership_expires_at": new_expires}
        ).eq("id", referrer_id).execute()

    # Notify referrer
    try:
        new_user = get_user(new_user_id)
        new_name = new_user.get("full_name") or new_user.get("username") or str(new_user_id) if new_user else str(new_user_id)
        msg = f"🎉 你邀请的 *{new_name}* 已注册！"
        if base:
            msg += f"\n\n奖励：会员延期 {REFERRAL_REWARD_DAYS} 天 ✅"
        await context.bot.send_message(
            chat_id=referrer_id, text=msg, parse_mode="Markdown",
        )
    except Exception:
        logger.warning("Failed to notify referrer %s", referrer_id)

    # Notify admins
    for admin_id in get_admin_ids():
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🔗 邀请记录：`{referrer_id}` 邀请了 `{new_user_id}`",
                parse_mode="Markdown",
            )
        except Exception:
            pass

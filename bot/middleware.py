"""
Middleware decorators applied to feature handlers.
- require_membership: blocks non-members (with free tier preview for some features)
- require_usage_quota: blocks users over daily limit (tier-aware)
"""
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from db.users import get_user, is_member, check_and_increment_usage, upsert_user
from config.settings import DAILY_USAGE_LIMIT

_JOIN_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("💰 开通会员", callback_data="join_member")],
    [InlineKeyboardButton("🔑 我有激活码", callback_data="feature_activate")],
])

# 每日使用限额（按tier）
_TIER_LIMITS = {
    "free": 3,
    "member": 20,
    "vip": 999,
    "admin": 999,
}


def require_membership(func):
    """Decorator: only allow active members/admins."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg_user = update.effective_user
        user = get_user(tg_user.id)

        if not user:
            upsert_user(tg_user.id, tg_user.username, tg_user.full_name)
            user = get_user(tg_user.id)

        if not is_member(user):
            await update.effective_message.reply_text(
                "🔒 *此功能需要会员权限*\n\n"
                "开通会员即可解锁全部AI工具。\n\n"
                "💎 会员 $9.9/月 | 👑 私董会 $99/月",
                parse_mode="Markdown",
                reply_markup=_JOIN_KB,
            )
            return ConversationHandler.END

        return await func(update, context)
    return wrapper


def require_usage_quota(func):
    """Decorator: enforce daily Claude call limit (tier-aware)."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user = get_user(user_id)
        tier = (user or {}).get("membership_tier", "free")
        limit = _TIER_LIMITS.get(tier, DAILY_USAGE_LIMIT)

        allowed = check_and_increment_usage(user_id, limit)
        if not allowed:
            if tier == "free":
                await update.effective_message.reply_text(
                    f"⚡ 免费体验次数已用完（每天{_TIER_LIMITS['free']}次）\n\n"
                    "开通会员享每日20次，私董会无限使用 👇",
                    reply_markup=_JOIN_KB,
                )
            else:
                await update.effective_message.reply_text(
                    f"⚡ 今日使用次数已达上限（{limit}次）\n"
                    "明日自动重置，感谢理解。"
                )
            return ConversationHandler.END
        return await func(update, context)
    return wrapper


def auto_register(func):
    """Silently register new users (free tier) on any interaction."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg_user = update.effective_user
        if tg_user:
            upsert_user(tg_user.id, tg_user.username, tg_user.full_name)
        return await func(update, context)
    return wrapper

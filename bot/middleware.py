"""
Middleware decorators applied to feature handlers.
- require_membership: blocks non-members
- require_usage_quota: blocks users over daily limit
"""
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from db.users import get_user, is_member, check_and_increment_usage, upsert_user
from config.settings import DAILY_USAGE_LIMIT


def require_membership(func):
    """Decorator: only allow active members/admins."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg_user = update.effective_user
        user = get_user(tg_user.id)

        if not user:
            # Auto-register but as free user
            upsert_user(tg_user.id, tg_user.username, tg_user.full_name)
            user = get_user(tg_user.id)

        if not is_member(user):
            await update.effective_message.reply_text(
                "🔒 *此功能需要会员权限*\n\n"
                "请联系 @laowang\\_admin 开通会员，解锁全部 AI 工具。\n\n"
                "发送 /start 查看功能介绍。",
                parse_mode="Markdown",
            )
            return ConversationHandler.END

        return await func(update, context)
    return wrapper


def require_usage_quota(func):
    """Decorator: enforce daily Claude call limit. Must be used AFTER require_membership."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        allowed = check_and_increment_usage(user_id)
        if not allowed:
            await update.effective_message.reply_text(
                f"⚡ 今日使用次数已达上限（{DAILY_USAGE_LIMIT} 次）\n"
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

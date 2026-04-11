"""
Middleware decorators applied to feature handlers.
- require_membership: blocks non-members (with free tier preview for some features)
- require_usage_quota: blocks users over daily limit (tier-aware)
- redirect_to_dm: in groups, redirect user to private chat
"""
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, ApplicationHandlerStop

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



# ── 群聊命令拦截：群里使用命令时，提示去私聊 ──────────────────────────────────

# 允许在群里直接执行的命令（群聊专用功能）
GROUP_ALLOWED_COMMANDS = {"mychat", "groupstats"}


async def group_command_redirect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """拦截群聊中的命令，引导用户去私聊使用。"""
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        return  # 私聊不拦截

    # 检查是否是允许在群里执行的命令
    if update.message and update.message.text:
        cmd = update.message.text.split()[0].lstrip("/").split("@")[0].lower()
        if cmd in GROUP_ALLOWED_COMMANDS:
            return  # 允许执行，不���截

    user = update.effective_user
    bot_me = await context.bot.get_me()
    name = user.first_name or user.username or "你"

    await update.message.reply_text(
        f"👋 *{name}*，请在私聊中使用此功能，保护你的隐私 🔒",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 打开私聊", url=f"https://t.me/{bot_me.username}?start=from_group")],
        ]),
    )
    # 阻止后续 handler 继续处理此命令
    raise ApplicationHandlerStop()

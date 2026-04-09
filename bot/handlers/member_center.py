"""
会员中心 — 连续天数 / 会员权益 / 邀请入口
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.middleware import require_membership
from db.points import get_points_info
from db.client import get_client


_BACK_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("← 返回会员中心", callback_data="menu_member")],
])


@require_membership
async def show_streaks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示所有连续天数。"""
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    db = get_client()

    # 通用签到连续天数
    info = get_points_info(user_id)
    checkin_streak = info.get("checkin_streak", 0) or 0

    # 健康连续天数
    user = db.table("users").select(
        "health_streak, gym_count"
    ).eq("id", user_id).maybe_single().execute()
    user_data = user.data or {}
    health_streak = user_data.get("health_streak", 0) or 0
    gym_count = user_data.get("gym_count", 0) or 0

    text = (
        "🔥 *我的连续天数*\n\n"
        f"✅ 每日签到: *{checkin_streak}* 天\n"
        f"❤️ 健康打卡: *{health_streak}* 天\n"
        f"🏋️ 累计训练: *{gym_count}* 次\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 坚持打卡，解锁更多成就和奖励！\n"
        "每天签到、健康打卡、健身打卡都能赚积分。"
    )

    reply = query.message.reply_text if query else update.message.reply_text
    await reply(text, parse_mode="Markdown", reply_markup=_BACK_KB)


@require_membership
async def show_membership_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示会员权益说明。"""
    query = update.callback_query
    if query:
        await query.answer()

    text = (
        "💎 *老王工具箱 — 会员权益*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🆓 *免费用户*\n"
        "• 每日签到赚积分\n"
        "• 查看排行榜\n"
        "• 基础功能预览\n\n"
        "💎 *会员用户*\n"
        "• 全部AI工具无限使用（每日20次）\n"
        "• 💰 创业财富: 交易复盘+爆款选题+口播脚本+品牌定位+销售助手+民宿工具\n"
        "• 💪 个人健康: AI训练计划+AI食谱+卡路里打卡+老王计划库\n"
        "• 🧠 个人成长: 认知训练+表达优化+英语升级+执行系统\n"
        "• 📰 每日情报: 早间简报+盘前盘后情报\n"
        "• 💡 老王持仓+投资策略查看\n"
        "• 🏆 挑战任务+战队+排行榜\n"
        "• 📋 成绩单生成+分享\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚡ *老王说：这不是订阅，是给自己的投资。*"
    )

    reply = query.message.reply_text if query else update.message.reply_text
    await reply(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 开通会员", callback_data="join_member")],
            [InlineKeyboardButton("← 返回会员中心", callback_data="menu_member")],
        ]),
    )


async def callback_invite_redirect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """邀请好友 — redirect to /invite command."""
    query = update.callback_query
    await query.answer()
    from bot.handlers.referral import cmd_invite
    # Simulate command by calling the handler directly
    await cmd_invite(update, context)

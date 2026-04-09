"""
Feature: 成绩单分享
生成本周健康成绩单，可复制分享到社交媒体。
"""
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.middleware import require_membership
from db.health import get_user_health_stats


_WANG_REPORT_QUOTES = [
    "纪律就是自由。",
    "身体是一切的底盘。",
    "每一天都在投票，投给未来的自己。",
    "最好的投资，是投资自己的身体。",
    "坚持本身就是一种天赋。",
]


@require_membership
async def show_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    stats = get_user_health_stats(user_id)

    today = date.today()
    week_num = today.isocalendar()[1]
    quote_idx = (user_id + today.toordinal()) % len(_WANG_REPORT_QUOTES)
    quote = _WANG_REPORT_QUOTES[quote_idx]

    rank_text = f"第{stats['rank']}名" if stats['rank'] > 0 else "未上榜"

    report = (
        f"📊 *老王健康执行系统 | 周报*\n\n"
        f"👤 *{stats['name']}* 的第{week_num}周成绩单\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏋️ 本周训练: {stats['week_gym']}次\n"
        f"🥗 饮食记录: {stats['week_cal_days']}/7天\n"
        f"❤️ 健康打卡: {stats['week_health']}/7天\n"
        f"🔥 连续打卡: {stats['health_streak']}天\n"
        f"🏋️ 累计训练: {stats['gym_count']}次\n"
        f"🪙 总积分: {stats['points']}\n\n"
        f"📈 排名: {rank_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ *老王说: {quote}*"
    )

    # 纯文本版本（方便复制分享）
    share_text = (
        f"📊 老王健康执行系统 | 周报\n\n"
        f"👤 {stats['name']} 的第{week_num}周成绩单\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏋️ 本周训练: {stats['week_gym']}次\n"
        f"🥗 饮食记录: {stats['week_cal_days']}/7天\n"
        f"❤️ 健康打卡: {stats['week_health']}/7天\n"
        f"🔥 连续打卡: {stats['health_streak']}天\n"
        f"📈 排名: {rank_text}\n\n"
        f"⚡ 老王说: {quote}\n\n"
        f"💪 加入老王健康执行系统，一起变强"
    )

    context.user_data["share_report"] = share_text

    reply = query.message.reply_text if query else update.message.reply_text
    await reply(
        report,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 复制分享文案", callback_data="copy_report")],
            [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
        ]),
    )


async def send_share_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """发送纯文本版成绩单，方便用户复制。"""
    query = update.callback_query
    await query.answer()

    share_text = context.user_data.get("share_report", "暂无数据")
    await query.message.reply_text(
        f"👇 *长按复制下方文案分享*\n\n"
        f"```\n{share_text}\n```",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
        ]),
    )

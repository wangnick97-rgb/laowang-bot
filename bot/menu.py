"""
/start command and main menu InlineKeyboard builder.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import logging
from bot.middleware import auto_register
from db.users import get_user, is_member, upsert_user, get_admin_ids

logger = logging.getLogger(__name__)

WELCOME_TEXT = """👋 *欢迎来到老王工具箱！*

这里有 10 个专为投资者、创业者、内容创作者打造的 AI 工具：

📊 投资复盘与市场情报
✍️ 爆款内容创作
🏠 Airbnb 运营辅助
🧠 商业定位与个人成长

每天早上还会自动推送 AI 财经简报 📰

点击下方按钮开始使用 👇"""

WELCOME_NON_MEMBER = """👋 *你好！我是老王工具箱。*

我为会员提供 10 个专业 AI 工具，涵盖：
• 📊 美股交易复盘 & 每日情报
• ✍️ 爆款短视频选题 & 口播稿
• 🏠 Airbnb 房源诊断 & 运营
• 🧠 个人商业定位 & 认知打卡

点击下方按钮了解如何开通 👇"""


def build_join_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 开通会员", callback_data="join_member")],
    ])


def build_main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📊 投资工具", callback_data="menu_invest"),
         InlineKeyboardButton("✍️ 创作工具", callback_data="menu_content")],
        [InlineKeyboardButton("🏠 Airbnb 工具", callback_data="menu_airbnb"),
         InlineKeyboardButton("🧠 个人成长", callback_data="menu_growth")],
        [InlineKeyboardButton("💪 健康执行系统", callback_data="menu_health")],
        [InlineKeyboardButton("📰 今日简报（立即获取）", callback_data="feature_news")],
        [InlineKeyboardButton("🎯 老王 1v1 私人咨询", callback_data="feature_consult")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_invest_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📈 交易复盘", callback_data="feature_trade")],
        [InlineKeyboardButton("🌅 盘前情报", callback_data="feature_premarket"),
         InlineKeyboardButton("🌆 盘后情报", callback_data="feature_postmarket")],
        [InlineKeyboardButton("← 返回主菜单", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_content_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🔥 爆款选题生成", callback_data="feature_topic")],
        [InlineKeyboardButton("🎙️ 口播稿/直播展开", callback_data="feature_script")],
        [InlineKeyboardButton("← 返回主菜单", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_airbnb_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🏡 房源可行性诊断", callback_data="feature_property")],
        [InlineKeyboardButton("💬 房东/客户文案", callback_data="feature_landlord")],
        [InlineKeyboardButton("← 返回主菜单", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_growth_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("💼 个人商业定位", callback_data="feature_brand")],
        [InlineKeyboardButton("🤝 销售/谈判/合同辅助", callback_data="feature_sales")],
        [InlineKeyboardButton("✅ 今日认知打卡", callback_data="feature_checkin")],
        [InlineKeyboardButton("← 返回主菜单", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_health_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🏋️ 今日训练", callback_data="feature_workout"),
         InlineKeyboardButton("🍽️ 今日食谱", callback_data="feature_meal")],
        [InlineKeyboardButton("🧮 蛋白质计算", callback_data="feature_protein"),
         InlineKeyboardButton("🔥 卡路里计算", callback_data="feature_calories")],
        [InlineKeyboardButton("💪 老王计划库", callback_data="feature_wangplan"),
         InlineKeyboardButton("🍫 零食白名单", callback_data="feature_snacks")],
        [InlineKeyboardButton("💊 老王补给", callback_data="feature_supplements"),
         InlineKeyboardButton("🥗 记录饮食", callback_data="feature_cal_log")],
        [InlineKeyboardButton("❤️ 健康打卡", callback_data="feature_health_checkin"),
         InlineKeyboardButton("🏃 健身打卡", callback_data="feature_gym_log")],
        [InlineKeyboardButton("🎯 挑战任务", callback_data="feature_challenge"),
         InlineKeyboardButton("👥 战队", callback_data="feature_team")],
        [InlineKeyboardButton("📊 排行榜", callback_data="feature_health_rank"),
         InlineKeyboardButton("📋 成绩单", callback_data="feature_report")],
        [InlineKeyboardButton("← 返回主菜单", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


MENU_MAP = {
    "menu_invest": ("📊 *投资工具*\n选择你需要的功能：", build_invest_menu),
    "menu_content": ("✍️ *创作工具*\n选择你需要的功能：", build_content_menu),
    "menu_airbnb": ("🏠 *Airbnb 工具*\n选择你需要的功能：", build_airbnb_menu),
    "menu_growth": ("🧠 *个人成长*\n选择你需要的功能：", build_growth_menu),
    "menu_health": ("💪 *老王健康执行系统*\n\n纪律就是自由。选择你需要的功能：", build_health_menu),
}


@auto_register
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    user = get_user(tg_user.id)
    is_new = not user

    # 处理邀请链接 deep link: /start ref_<referrer_id>
    referrer_id = None
    if is_new and context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0][4:])
        except ValueError:
            pass

    if user and is_member(user):
        await update.message.reply_text(
            WELCOME_TEXT,
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
    else:
        await update.message.reply_text(
            WELCOME_NON_MEMBER,
            parse_mode="Markdown",
            reply_markup=build_join_menu(),
        )

    # 新人引导（仅第一次触发）
    if is_new:
        import asyncio
        await asyncio.sleep(1.5)
        await update.message.reply_text(
            "📖 *快速上手指南*\n\n"
            "老王工具箱有 *10 个 AI 工具*，覆盖 4 大方向：\n\n"
            "📊 *投资* — 交易复盘、盘前盘后情报\n"
            "✍️ *内容* — 爆款选题、短视频脚本\n"
            "🏠 *Airbnb* — 房源诊断、沟通话术\n"
            "🧠 *成长* — 品牌定位、销售辅助、每日打卡\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🚀 *推荐你先试试这 3 个：*\n\n"
            "1️⃣ /checkin — 每日签到，积累积分\n"
            "2️⃣ /news — 获取今日 AI 财经简报\n"
            "3️⃣ /topic — 用 AI 生成爆款选题\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "💡 *小贴士*\n"
            "• 每天签到可以赚积分，积分可兑换会员天数\n"
            "• 发送 /points 查看积分和积分商城\n"
            "• 发送 /invite 获取你的专属邀请链接\n"
            "• 发送 /menu 随时返回主菜单",
            parse_mode="Markdown",
        )

    # 处理邀请奖励
    if is_new and referrer_id:
        from bot.handlers.referral import process_referral
        await process_referral(context, tg_user.id, referrer_id)

    # 通知管理员有新用户
    if is_new:
        name = tg_user.full_name or tg_user.username or str(tg_user.id)
        uname = f"@{tg_user.username}" if tg_user.username else "无用户名"
        notify_text = (
            f"🆕 *新用户*\n"
            f"姓名：{name}\n"
            f"用户名：{uname}\n"
            f"ID：`{tg_user.id}`\n\n"
            f"快速开通：`/addmember {tg_user.id} {name}`"
        )
        for admin_id in get_admin_ids():
            try:
                await context.bot.send_message(
                    chat_id=admin_id, text=notify_text, parse_mode="Markdown",
                )
            except Exception:
                logger.warning("Failed to notify admin %s", admin_id)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user or not is_member(user):
        await update.message.reply_text(
            "发送 /start 了解更多信息。",
        )
        return
    await update.message.reply_text(
        "🏠 *主菜单*\n选择你需要的工具：",
        parse_mode="Markdown",
        reply_markup=build_main_menu(),
    )


async def handle_menu_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all menu_* callback queries (sub-menu navigation)."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "menu_main":
        await query.edit_message_text(
            "🏠 *主菜单*\n选择你需要的工具：",
            parse_mode="Markdown",
            reply_markup=build_main_menu(),
        )
        return

    if data in MENU_MAP:
        text, keyboard_fn = MENU_MAP[data]
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=keyboard_fn(),
        )

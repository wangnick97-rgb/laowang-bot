"""
/start command and main menu InlineKeyboard builder.
4-section architecture: 创业财富 / 个人健康 / 个人成长 / 会员中心
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

import logging
from bot.middleware import auto_register
from db.users import get_user, is_member, upsert_user, get_admin_ids

logger = logging.getLogger(__name__)

WELCOME_TEXT = """👋 *欢迎来到老王工具箱！*

你的人生操作系统——赚钱、健身、成长，一个Bot搞定。

💰 创业财富 — 赚钱工具+投资情报
💪 个人健康 — 训练+饮食+打卡
🧠 个人成长 — 认知+表达+英语+执行
👤 会员中心 — 积分+排行+奖励

点击下方按钮开始 👇"""

WELCOME_NON_MEMBER = """👋 *你好！我是老王工具箱。*

专为创业者、投资者打造的AI人生操作系统：
• 💰 创业财富 — AI商业工具+美股情报
• 💪 个人健康 — 训练食谱+打卡系统
• 🧠 个人成长 — 认知表达+英语执行
• 👤 会员中心 — 积分排行+社群

点击下方按钮了解如何开通 👇"""


def build_join_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 开通会员", callback_data="join_member")],
        [InlineKeyboardButton("🔑 我有激活码", callback_data="feature_activate")],
    ])


# ── 主菜单（4板块）────────────────────────────────────────────────────────────

def build_main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("💰 创业财富", callback_data="menu_wealth"),
         InlineKeyboardButton("💪 个人健康", callback_data="menu_health")],
        [InlineKeyboardButton("🧠 个人成长", callback_data="menu_growth"),
         InlineKeyboardButton("👤 会员中心", callback_data="menu_member")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ── 创业财富 ──────────────────────────────────────────────────────────────────

def build_wealth_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📰 今日情报", callback_data="menu_intel"),
         InlineKeyboardButton("✍️ 创业工具", callback_data="menu_biz_tools")],
        [InlineKeyboardButton("📈 投资工具", callback_data="menu_invest"),
         InlineKeyboardButton("🗳️ 每日投票", callback_data="feature_vote")],
        [InlineKeyboardButton("← 返回主菜单", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_intel_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🌅 早间财富简报", callback_data="feature_news")],
        [InlineKeyboardButton("📊 盘前情报", callback_data="feature_premarket"),
         InlineKeyboardButton("📉 盘后复盘", callback_data="feature_postmarket")],
        [InlineKeyboardButton("← 返回创业财富", callback_data="menu_wealth")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_biz_tools_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🔥 爆款选题", callback_data="feature_topic"),
         InlineKeyboardButton("🎙️ 口播脚本", callback_data="feature_script")],
        [InlineKeyboardButton("💼 品牌定位", callback_data="feature_brand"),
         InlineKeyboardButton("🤝 销售助手", callback_data="feature_sales")],
        [InlineKeyboardButton("🏡 民宿诊断", callback_data="feature_property"),
         InlineKeyboardButton("💬 民宿话术", callback_data="feature_landlord")],
        [InlineKeyboardButton("← 返回创业财富", callback_data="menu_wealth")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_invest_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📊 交易复盘", callback_data="feature_trade")],
        [InlineKeyboardButton("💡 老王持仓", callback_data="feature_wang_portfolio"),
         InlineKeyboardButton("📋 投资策略", callback_data="feature_wang_strategy")],
        [InlineKeyboardButton("🏦 美股开户教程", callback_data="feature_us_stock_guide")],
        [InlineKeyboardButton("← 返回创业财富", callback_data="menu_wealth")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ── 个人健康 ──────────────────────────────────────────────────────────────────

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
        [InlineKeyboardButton("📊 排行榜", callback_data="feature_health_rank"),
         InlineKeyboardButton("👥 战队", callback_data="feature_team")],
        [InlineKeyboardButton("← 返回主菜单", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ── 个人成长 ──────────────────────────────────────────────────────────────────

def build_growth_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("💡 认知系统", callback_data="menu_cognition"),
         InlineKeyboardButton("🗣️ 表达系统", callback_data="menu_expression")],
        [InlineKeyboardButton("🌍 英语系统", callback_data="menu_english"),
         InlineKeyboardButton("⚡ 执行系统", callback_data="menu_execution")],
        [InlineKeyboardButton("← 返回主菜单", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_cognition_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("💡 今日认知", callback_data="feature_daily_cognition")],
        [InlineKeyboardButton("🧭 决策助手", callback_data="feature_decision")],
        [InlineKeyboardButton("🌙 晚间复盘", callback_data="feature_evening_review")],
        [InlineKeyboardButton("← 返回个人成长", callback_data="menu_growth")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_expression_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🗣️ 表达优化器", callback_data="feature_text_optimizer")],
        [InlineKeyboardButton("💼 商务回复助手", callback_data="feature_biz_reply")],
        [InlineKeyboardButton("🎙️ 口播稿优化", callback_data="feature_script_polish")],
        [InlineKeyboardButton("← 返回个人成长", callback_data="menu_growth")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_english_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📝 今日英语升级", callback_data="feature_daily_english")],
        [InlineKeyboardButton("🔄 中式英语改写", callback_data="feature_chinglish_fix")],
        [InlineKeyboardButton("💬 商务英语对话", callback_data="feature_biz_english")],
        [InlineKeyboardButton("← 返回个人成长", callback_data="menu_growth")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_execution_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📋 今日计划", callback_data="feature_daily_plan"),
         InlineKeyboardButton("🔥 深度工作打卡", callback_data="feature_deep_work")],
        [InlineKeyboardButton("🧨 拖延破解器", callback_data="feature_procrastination")],
        [InlineKeyboardButton("🎯 21天挑战", callback_data="feature_21day")],
        [InlineKeyboardButton("← 返回个人成长", callback_data="menu_growth")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ── 会员中心 ──────────────────────────────────────────────────────────────────

def build_member_menu() -> InlineKeyboardMarkup:
    from config.settings import WEBAPP_URL
    keyboard = []

    # Mini App 数据面板按钮（仅在配置了WEBAPP_URL时显示）
    if WEBAPP_URL:
        keyboard.append([InlineKeyboardButton(
            "📊 数据面板",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}/webapp/index.html"),
        )])

    keyboard.extend([
        [InlineKeyboardButton("🪙 我的积分", callback_data="feature_points"),
         InlineKeyboardButton("🔥 连续天数", callback_data="feature_streaks")],
        [InlineKeyboardButton("🎖️ 我的成就", callback_data="my_badges"),
         InlineKeyboardButton("📋 成绩单", callback_data="feature_report")],
        [InlineKeyboardButton("🏆 排行榜", callback_data="checkin_leaderboard"),
         InlineKeyboardButton("🎁 奖励中心", callback_data="menu_rewards")],
        [InlineKeyboardButton("💎 会员权益", callback_data="feature_membership_info"),
         InlineKeyboardButton("👥 邀请好友", callback_data="feature_invite")],
        [InlineKeyboardButton("✅ 每日签到", callback_data="feature_checkin"),
         InlineKeyboardButton("🎯 1v1咨询", callback_data="feature_consult")],
        [InlineKeyboardButton("← 返回主菜单", callback_data="menu_main")],
    ])
    return InlineKeyboardMarkup(keyboard)


def build_rewards_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🛍️ 积分商城", callback_data="feature_points")],
        [InlineKeyboardButton("🎯 挑战任务", callback_data="feature_challenge")],
        [InlineKeyboardButton("👥 邀请好友", callback_data="feature_invite")],
        [InlineKeyboardButton("← 返回会员中心", callback_data="menu_member")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ── 菜单路由表 ────────────────────────────────────────────────────────────────

MENU_MAP = {
    # 顶层
    "menu_wealth": ("💰 *创业财富*\n\n赚钱是最大的自律。选择你需要的工具：", build_wealth_menu),
    "menu_health": ("💪 *个人健康*\n\n纪律就是自由。选择你需要的功能：", build_health_menu),
    "menu_growth": ("🧠 *个人成长*\n\n每天进步1%。选择你的训练系统：", build_growth_menu),
    "menu_member": ("👤 *会员中心*\n\n你的成长仪表盘：", build_member_menu),
    # 创业财富子菜单
    "menu_intel": ("📰 *今日情报*\n\n每天的财富信息差：", build_intel_menu),
    "menu_biz_tools": ("✍️ *创业工具*\n\n执行级AI武器库：", build_biz_tools_menu),
    "menu_invest": ("📈 *投资工具*\n\n数据驱动，不赌不猜：", build_invest_menu),
    # 个人成长子菜单
    "menu_cognition": ("💡 *认知系统*\n\n每天一次认知训练：", build_cognition_menu),
    "menu_expression": ("🗣️ *表达系统*\n\n说得好比想得好更重要：", build_expression_menu),
    "menu_english": ("🌍 *英语系统*\n\n国际化从表达开始：", build_english_menu),
    "menu_execution": ("⚡ *执行系统*\n\n想到就做到：", build_execution_menu),
    # 会员中心子菜单
    "menu_rewards": ("🎁 *奖励中心*\n\n用努力兑换回报：", build_rewards_menu),
}


# ── /start command ────────────────────────────────────────────────────────────

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

    # 新人引导
    if is_new:
        import asyncio
        await asyncio.sleep(1.5)
        await update.message.reply_text(
            "📖 *快速上手指南*\n\n"
            "老王工具箱 = 你的人生操作系统\n\n"
            "💰 *创业财富* — 交易复盘、爆款选题、投资情报\n"
            "💪 *个人健康* — AI训练计划、食谱、打卡\n"
            "🧠 *个人成长* — 认知训练、表达优化、英语升级\n"
            "👤 *会员中心* — 积分、排行、挑战、奖励\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🚀 *推荐先试试：*\n\n"
            "1️⃣ /checkin — 每日签到，积累积分\n"
            "2️⃣ /news — 获取今日AI财经简报\n"
            "3️⃣ /workout — AI生成训练计划\n"
            "4️⃣ /topic — AI生成爆款选题\n\n"
            "💡 发送 /menu 随时返回主菜单",
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
        await update.message.reply_text("发送 /start 了解更多信息。")
        return
    await update.message.reply_text(
        "🏠 *主菜单*\n选择你需要的板块：",
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
            "🏠 *主菜单*\n选择你需要的板块：",
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

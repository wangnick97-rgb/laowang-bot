"""
/start command and main menu InlineKeyboard builder.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.middleware import auto_register
from db.users import get_user, is_member, upsert_user

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

*如需开通会员，请联系：@laowang\\_admin*"""


def build_main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📊 投资工具", callback_data="menu_invest"),
         InlineKeyboardButton("✍️ 创作工具", callback_data="menu_content")],
        [InlineKeyboardButton("🏠 Airbnb 工具", callback_data="menu_airbnb"),
         InlineKeyboardButton("🧠 个人成长", callback_data="menu_growth")],
        [InlineKeyboardButton("📰 今日简报（立即获取）", callback_data="feature_news")],
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


MENU_MAP = {
    "menu_invest": ("📊 *投资工具*\n选择你需要的功能：", build_invest_menu),
    "menu_content": ("✍️ *创作工具*\n选择你需要的功能：", build_content_menu),
    "menu_airbnb": ("🏠 *Airbnb 工具*\n选择你需要的功能：", build_airbnb_menu),
    "menu_growth": ("🧠 *个人成长*\n选择你需要的功能：", build_growth_menu),
}


@auto_register
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
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
        )


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

"""
Stub handlers for Phase 2 features.
These show a "coming soon" message so the menu buttons don't produce errors.
Replace each stub with a real handler as you build Phase 2.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

_BACK = InlineKeyboardMarkup([[InlineKeyboardButton("← 返回主菜单", callback_data="menu_main")]])

COMING_SOON = "🚧 *即将上线*\n\n这个功能正在开发中，敬请期待！"


async def stub_premarket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(COMING_SOON, parse_mode="Markdown", reply_markup=_BACK)


async def stub_postmarket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(COMING_SOON, parse_mode="Markdown", reply_markup=_BACK)


async def stub_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(COMING_SOON, parse_mode="Markdown", reply_markup=_BACK)


async def stub_brand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(COMING_SOON, parse_mode="Markdown", reply_markup=_BACK)


async def stub_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(COMING_SOON, parse_mode="Markdown", reply_markup=_BACK)


async def stub_property(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(COMING_SOON, parse_mode="Markdown", reply_markup=_BACK)


async def stub_landlord(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(COMING_SOON, parse_mode="Markdown", reply_markup=_BACK)


async def stub_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(COMING_SOON, parse_mode="Markdown", reply_markup=_BACK)

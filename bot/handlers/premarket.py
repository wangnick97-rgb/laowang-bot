"""
Feature: 盘前简报 — 自动抓取市场数据 + Claude 分析
Entry: callback feature_premarket (no user input needed)
"""
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.middleware import require_membership, require_usage_quota
from services.market_data import get_market_snapshot, format_snapshot_for_claude
from services.claude_client import call_claude

_FEATURE_KEY = "market_intel_pre"


def _back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 刷新", callback_data="feature_premarket"),
        InlineKeyboardButton("← 主菜单", callback_data="menu_main"),
    ]])


@require_membership
@require_usage_quota
async def callback_premarket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🌅 正在抓取盘前数据，稍等...")

    snapshot = get_market_snapshot()
    market_text = format_snapshot_for_claude(snapshot)
    date_str = datetime.now().strftime("%Y年%m月%d日")

    result = await call_claude(
        _FEATURE_KEY,
        market_text,
        user_id=update.effective_user.id,
        max_tokens=900,
        extra_context=f"当前时间（美东）：{date_str}",
    )

    await query.message.reply_text(
        result,
        parse_mode="Markdown",
        reply_markup=_back_button(),
    )

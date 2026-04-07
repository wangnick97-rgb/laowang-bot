"""
Feature: 每日新闻简报
- /news command or "feature_news" callback
- Fetches today's cached summary (or generates it live)
"""
from datetime import date, datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.middleware import require_membership, require_usage_quota
from db.news_cache import get_cached_summary, save_cache
from services.news_fetcher import fetch_daily_news, format_articles_for_claude
from services.claude_client import call_claude


def _back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("← 返回主菜单", callback_data="menu_main")
    ]])


@require_membership
@require_usage_quota
async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _deliver_news_brief(update.message.reply_text, update.effective_user.id)


@require_membership
@require_usage_quota
async def callback_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ 正在获取今日简报，请稍候...")
    await _deliver_news_brief(
        lambda text, **kw: query.message.reply_text(text, **kw),
        update.effective_user.id,
    )


async def _deliver_news_brief(reply_fn, user_id: int):
    today = date.today()
    summary = get_cached_summary("brief", today)

    if not summary:
        await reply_fn("⏳ 正在抓取最新资讯并整理，稍等一下...")
        articles = fetch_daily_news()
        if not articles:
            await reply_fn("😕 今日新闻抓取失败，请稍后再试。")
            return
        date_str = datetime.now().strftime("%Y年%m月%d日")
        raw_text = format_articles_for_claude(articles)
        summary = await call_claude(
            "news_brief",
            raw_text,
            user_id=user_id,
            max_tokens=1200,
            extra_context=f"今天是美东时间 {date_str}",
        )
        save_cache("brief", articles, summary, today)

    header = "📰 *老王早报* | 今日要闻\n\n"
    await reply_fn(
        header + summary,
        parse_mode="Markdown",
        reply_markup=_back_button(),
    )

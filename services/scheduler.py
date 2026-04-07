"""
APScheduler setup — all recurring jobs defined here.
Called once at bot startup from main.py.
"""
import asyncio
import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot
from telegram.error import TelegramError

from config.settings import SCHEDULER_TIMEZONE
from db.users import get_all_active_members
from db.news_cache import get_cached_summary, save_cache
from services.news_fetcher import fetch_daily_news, format_articles_for_claude
from services.market_data import get_market_snapshot, format_snapshot_for_claude
from services.claude_client import call_claude

logger = logging.getLogger(__name__)

_SYSTEM_USER_ID = 0  # Placeholder user_id for scheduled Claude calls


async def _broadcast(bot: Bot, text: str, job_name: str):
    """Send a message to all active members with rate-limit protection."""
    members = get_all_active_members()
    reached = 0
    for i, member in enumerate(members):
        try:
            await bot.send_message(
                chat_id=member["id"],
                text=text,
                parse_mode="Markdown",
            )
            reached += 1
        except TelegramError as e:
            logger.warning("Broadcast skipped user %s: %s", member["id"], e)
        # Telegram rate limit: ~30 msgs/sec. Send 20/sec to stay safe.
        if i > 0 and i % 20 == 0:
            await asyncio.sleep(1)

    logger.info("%s broadcast complete: %d/%d members reached", job_name, reached, len(members))


async def job_daily_news_brief(bot: Bot):
    today = date.today()
    summary = get_cached_summary("brief", today)
    if not summary:
        articles = fetch_daily_news()
        if not articles:
            logger.warning("daily_news_brief: no articles fetched")
            return
        from datetime import datetime
        date_str = datetime.now().strftime("%Y年%m月%d日")
        raw_text = format_articles_for_claude(articles)
        summary = await call_claude(
            "news_brief",
            raw_text,
            user_id=_SYSTEM_USER_ID,
            max_tokens=1200,
            extra_context=f"今天是美东时间 {date_str}",
        )
        save_cache("brief", articles, summary, today)

    header = "📰 *老王早报* | 今日要闻\n\n"
    await _broadcast(bot, header + summary, "daily_news_brief")


async def job_premarket_intel(bot: Bot):
    today = date.today()
    summary = get_cached_summary("premarket", today)
    if not summary:
        snapshot = get_market_snapshot()
        market_text = format_snapshot_for_claude(snapshot)
        from datetime import datetime
        date_str = datetime.now().strftime("%Y年%m月%d日")
        summary = await call_claude(
            "market_intel_pre",
            market_text,
            user_id=_SYSTEM_USER_ID,
            max_tokens=800,
            extra_context=f"当前日期：{date_str}",
        )
        save_cache("premarket", [], summary, today)

    await _broadcast(bot, summary, "premarket_intel")


async def job_postmarket_intel(bot: Bot):
    today = date.today()
    summary = get_cached_summary("postmarket", today)
    if not summary:
        snapshot = get_market_snapshot()
        market_text = format_snapshot_for_claude(snapshot)
        from datetime import datetime
        date_str = datetime.now().strftime("%Y年%m月%d日")
        summary = await call_claude(
            "market_intel_post",
            market_text,
            user_id=_SYSTEM_USER_ID,
            max_tokens=800,
            extra_context=f"当前日期：{date_str}",
        )
        save_cache("postmarket", [], summary, today)

    await _broadcast(bot, summary, "postmarket_intel")


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=SCHEDULER_TIMEZONE)

    # Daily news brief — 8:30 AM ET every day
    scheduler.add_job(
        lambda: asyncio.create_task(job_daily_news_brief(bot)),
        CronTrigger(hour=8, minute=30, timezone=SCHEDULER_TIMEZONE),
        id="daily_news_brief",
        replace_existing=True,
    )

    # Pre-market intel — 9:00 AM ET weekdays
    scheduler.add_job(
        lambda: asyncio.create_task(job_premarket_intel(bot)),
        CronTrigger(hour=9, minute=0, day_of_week="mon-fri", timezone=SCHEDULER_TIMEZONE),
        id="premarket_intel",
        replace_existing=True,
    )

    # Post-market intel — 4:30 PM ET weekdays
    scheduler.add_job(
        lambda: asyncio.create_task(job_postmarket_intel(bot)),
        CronTrigger(hour=16, minute=30, day_of_week="mon-fri", timezone=SCHEDULER_TIMEZONE),
        id="postmarket_intel",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))
    return scheduler

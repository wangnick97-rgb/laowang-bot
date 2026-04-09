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
from db.users import get_all_active_members, get_expiring_members
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


async def job_membership_reminder(bot: Bot):
    """Remind members whose membership expires within 3 days."""
    expiring = get_expiring_members(days=3)
    for member in expiring:
        try:
            await bot.send_message(
                chat_id=member["id"],
                text=(
                    "⏰ *会员到期提醒*\n\n"
                    "你的老王工具箱会员即将到期，续费后可继续使用全部 AI 工具。\n\n"
                    "请联系 @scorpia2004 续费 🙏"
                ),
                parse_mode="Markdown",
            )
        except TelegramError as e:
            logger.warning("Expiry reminder skipped user %s: %s", member["id"], e)
    logger.info("membership_reminder: notified %d expiring members", len(expiring))


async def job_daily_cognition(bot: Bot):
    """推送今日认知主题+思考题给所有会员。"""
    from bot.handlers.daily_cognition import _TOPICS
    idx = date.today().toordinal() % len(_TOPICS)
    topic = _TOPICS[idx]

    text = (
        f"💡 *今日认知* | {date.today().strftime('%m月%d日')}\n\n"
        f"📌 *{topic['title']}*\n\n"
        f"{topic['desc']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"❓ *今日思考题：*\n"
        f"{topic['question']}\n\n"
        f"👉 发送 /cognition 回答，可得5积分"
    )
    await _broadcast(bot, text, "daily_cognition")


async def job_daily_english(bot: Bot):
    """推送今日英语表达给所有会员。"""
    from bot.handlers.daily_english import _EXPRESSIONS
    idx = date.today().toordinal() % len(_EXPRESSIONS)
    expr = _EXPRESSIONS[idx]

    examples_text = "\n".join(f"  • {e}" for e in expr["examples"])
    text = (
        f"📝 *今日英语升级*\n\n"
        f"🎯 今日表达: *{expr['phrase']}*\n\n"
        f"❌ 中式: {expr['wrong']}\n"
        f"✅ 地道: {expr['right']}\n\n"
        f"📖 含义: {expr['meaning']}\n\n"
        f"💬 例句:\n{examples_text}\n\n"
        f"👉 发送 /english 用这个表达造句练习，可得3积分"
    )
    await _broadcast(bot, text, "daily_english")


async def job_evening_reminder(bot: Bot):
    """晚间复盘+执行检查提醒。"""
    text = (
        "🌙 *晚间提醒*\n\n"
        "今天过得怎么样？花2分钟给自己做个复盘：\n\n"
        "👉 /review — 晚间复盘（3个问题，+5积分）\n"
        "👉 /health — 健康打卡\n"
        "👉 /gym — 健身打卡（如果今天练了）\n\n"
        "⚡ 老王说：复盘不是为了自责，是为了明天更精准。"
    )
    await _broadcast(bot, text, "evening_reminder")


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

    # Membership expiry reminder — 10:00 AM ET daily
    scheduler.add_job(
        lambda: asyncio.create_task(job_membership_reminder(bot)),
        CronTrigger(hour=10, minute=0, timezone=SCHEDULER_TIMEZONE),
        id="membership_reminder",
        replace_existing=True,
    )

    # 今日认知 — 9:00 AM ET daily
    scheduler.add_job(
        lambda: asyncio.create_task(job_daily_cognition(bot)),
        CronTrigger(hour=9, minute=0, timezone=SCHEDULER_TIMEZONE),
        id="daily_cognition",
        replace_existing=True,
    )

    # 今日英语升级 — 12:00 PM ET daily
    scheduler.add_job(
        lambda: asyncio.create_task(job_daily_english(bot)),
        CronTrigger(hour=12, minute=0, timezone=SCHEDULER_TIMEZONE),
        id="daily_english",
        replace_existing=True,
    )

    # 晚间复盘提醒 — 9:00 PM ET daily
    scheduler.add_job(
        lambda: asyncio.create_task(job_evening_reminder(bot)),
        CronTrigger(hour=21, minute=0, timezone=SCHEDULER_TIMEZONE),
        id="evening_reminder",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))
    return scheduler

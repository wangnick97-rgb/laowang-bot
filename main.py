"""
老王工具箱 — Telegram Bot 入口
Usage:
  本地开发: python main.py            (polling mode, reads BOT_MODE from .env)
  生产部署: BOT_MODE=webhook python main.py
"""
import logging
import asyncio

from telegram import BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from config.settings import TELEGRAM_BOT_TOKEN, BOT_MODE, WEBHOOK_URL, PORT
from bot.menu import cmd_start, cmd_menu, handle_menu_navigation
from bot.handlers.news_brief import cmd_news, callback_news
from bot.handlers.trade_review import build_handler as trade_handler
from bot.handlers.viral_topic import build_handler as topic_handler
from bot.handlers.premarket import callback_premarket
from bot.handlers.postmarket import callback_postmarket
from bot.handlers.script_gen import build_handler as script_handler
from bot.handlers.brand_positioning import build_handler as brand_handler
from bot.handlers.sales_assist import build_handler as sales_handler
from bot.handlers.property_diag import build_handler as property_handler
from bot.handlers.landlord_msg import build_handler as landlord_handler
from bot.handlers.daily_checkin import build_handler as checkin_handler, show_leaderboard, show_badges
from bot.handlers.daily_poll import cmd_vote, callback_vote
from bot.handlers.admin import cmd_addmember, cmd_removemember, cmd_members, cmd_stats
from bot.handlers.join import callback_join
from bot.handlers.referral import cmd_invite
from bot.handlers.consultation import build_handler as consult_handler
from bot.handlers.points_shop import cmd_points, callback_redeem
from bot.handlers.protein_calc import build_handler as protein_handler
from bot.handlers.calorie_calc import build_handler as calorie_handler
from bot.handlers.wang_snacks import show_snacks
from bot.handlers.wang_supplements import show_supplements
from bot.handlers.gym_checkin import build_handler as gym_handler
from bot.handlers.health_checkin import build_handler as health_checkin_handler, show_health_rank
from bot.handlers.workout_plan import build_handler as workout_handler
from bot.handlers.meal_plan import build_handler as meal_handler
from bot.handlers.calorie_log import build_handler as calorie_log_handler
from bot.handlers.wang_plans import show_plan_menu, show_plan_detail
from bot.handlers.challenges import show_challenges, callback_join_challenge
from bot.handlers.team import build_handler as team_handler, show_team, show_team_rank
from bot.handlers.health_report import show_report, send_share_text
from services.scheduler import setup_scheduler

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("start", "开始 / 主菜单"),
    BotCommand("menu", "返回主菜单"),
    BotCommand("trade", "📈 交易复盘"),
    BotCommand("news", "📰 今日简报"),
    BotCommand("topic", "🔥 爆款选题"),
    BotCommand("script", "✍️ 短视频脚本"),
    BotCommand("brand", "🏷️ 品牌定位"),
    BotCommand("sales", "📋 销售话术"),
    BotCommand("property", "🏠 房源诊断"),
    BotCommand("landlord", "💬 房东话术"),
    BotCommand("checkin", "🌱 每日签到打卡"),
    BotCommand("points", "🪙 我的积分"),
    BotCommand("vote", "🗳️ 每日投票"),
    BotCommand("badges", "🎖️ 我的成就"),
    BotCommand("consult", "🎯 1v1 私人咨询"),
    BotCommand("invite", "🎁 邀请好友"),
    BotCommand("workout", "🏋️ 今日训练计划"),
    BotCommand("meal", "🍽️ 今日食谱"),
    BotCommand("callog", "🥗 记录饮食"),
    BotCommand("protein", "🧮 蛋白质计算"),
    BotCommand("calories", "🔥 卡路里计算"),
    BotCommand("gym", "🏃 健身打卡"),
    BotCommand("health", "❤️ 健康打卡"),
    BotCommand("challenge", "🎯 挑战任务"),
    BotCommand("team", "👥 我的战队"),
    BotCommand("report", "📋 健康成绩单"),
    BotCommand("cancel", "取消当前操作"),
    BotCommand("help", "使用说明"),
]


async def cmd_help(update, context):
    await update.message.reply_text(
        "*老王工具箱使用说明*\n\n"
        "/start — 开始/主菜单\n"
        "/trade — 交易复盘\n"
        "/news — 今日财经简报\n"
        "/topic — 爆款选题生成\n"
        "/cancel — 取消当前对话\n"
        "/menu — 返回主菜单\n\n"
        "每天 8:30 AM（美东时间）自动推送财经简报。\n"
        "有问题联系 @scorpia2004",
        parse_mode="Markdown",
    )


def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # ── Core commands ──────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("news", cmd_news))

    # ── Admin commands ────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("addmember", cmd_addmember))
    app.add_handler(CommandHandler("removemember", cmd_removemember))
    app.add_handler(CommandHandler("members", cmd_members))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("invite", cmd_invite))
    app.add_handler(CommandHandler("points", cmd_points))
    app.add_handler(CommandHandler("vote", cmd_vote))
    app.add_handler(CommandHandler("badges", lambda u, c: show_badges(u, c)))

    # ── ConversationHandlers (must be added before generic CallbackQueryHandlers)
    app.add_handler(trade_handler())
    app.add_handler(topic_handler())
    app.add_handler(script_handler())
    app.add_handler(brand_handler())
    app.add_handler(sales_handler())
    app.add_handler(property_handler())
    app.add_handler(landlord_handler())
    app.add_handler(checkin_handler())
    app.add_handler(consult_handler())
    app.add_handler(protein_handler())
    app.add_handler(calorie_handler())
    app.add_handler(gym_handler())
    app.add_handler(health_checkin_handler())
    app.add_handler(workout_handler())
    app.add_handler(meal_handler())
    app.add_handler(calorie_log_handler())
    app.add_handler(team_handler())

    # ── Menu navigation (sub-menu callbacks) ─────────────────────────────────
    app.add_handler(CallbackQueryHandler(
        handle_menu_navigation,
        pattern="^menu_",
    ))

    # ── Feature callbacks (news, stubs) ───────────────────────────────────────
    app.add_handler(CallbackQueryHandler(callback_news, pattern="^feature_news$"))
    app.add_handler(CallbackQueryHandler(callback_premarket, pattern="^feature_premarket$"))
    app.add_handler(CallbackQueryHandler(callback_postmarket, pattern="^feature_postmarket$"))
    app.add_handler(CallbackQueryHandler(callback_join, pattern="^join_member$"))
    app.add_handler(CallbackQueryHandler(show_leaderboard, pattern="^checkin_leaderboard$"))
    app.add_handler(CallbackQueryHandler(callback_redeem, pattern="^redeem_"))
    app.add_handler(CallbackQueryHandler(show_badges, pattern="^my_badges$"))
    app.add_handler(CallbackQueryHandler(callback_vote, pattern="^vote_\\d+$"))

    # ── Health module callbacks ──────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(show_snacks, pattern="^feature_snacks$"))
    app.add_handler(CallbackQueryHandler(show_supplements, pattern="^feature_supplements$"))
    app.add_handler(CallbackQueryHandler(show_health_rank, pattern="^feature_health_rank$"))

    # ── Health Phase 2 callbacks ────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(show_plan_menu, pattern="^feature_wangplan$"))
    app.add_handler(CallbackQueryHandler(show_plan_detail, pattern="^wplan_"))

    # ── Health Phase 3 callbacks ────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(show_challenges, pattern="^feature_challenge$"))
    app.add_handler(CallbackQueryHandler(callback_join_challenge, pattern="^join_challenge_"))
    app.add_handler(CallbackQueryHandler(show_team, pattern="^feature_team$"))
    app.add_handler(CallbackQueryHandler(show_team_rank, pattern="^team_rank$"))
    app.add_handler(CallbackQueryHandler(show_report, pattern="^feature_report$"))
    app.add_handler(CallbackQueryHandler(send_share_text, pattern="^copy_report$"))

    # ── Command shortcuts for Phase 3 ──────────────────────────────────────
    app.add_handler(CommandHandler("challenge", show_challenges))
    app.add_handler(CommandHandler("team", show_team))
    app.add_handler(CommandHandler("report", show_report))

    return app


async def post_init(app: Application):
    await app.bot.set_my_commands(BOT_COMMANDS)
    setup_scheduler(app.bot)
    logger.info("Bot initialized. Mode: %s", BOT_MODE)


def main():
    app = build_app()

    if BOT_MODE == "webhook" and WEBHOOK_URL:
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TELEGRAM_BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}",
            allowed_updates=["message", "callback_query"],
        )
    else:
        logger.info("Starting in polling mode (local dev)...")
        app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()

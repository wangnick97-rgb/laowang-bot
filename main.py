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
from bot.handlers.stubs import (
    stub_premarket, stub_postmarket,
    stub_script, stub_brand, stub_sales,
    stub_property, stub_landlord, stub_checkin,
)
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
        "有问题联系 @laowang\\_admin",
        parse_mode="Markdown",
    )


def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # ── Core commands ──────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("news", cmd_news))

    # ── ConversationHandlers (must be added before generic CallbackQueryHandlers)
    app.add_handler(trade_handler())
    app.add_handler(topic_handler())

    # ── Menu navigation (sub-menu callbacks) ─────────────────────────────────
    app.add_handler(CallbackQueryHandler(
        handle_menu_navigation,
        pattern="^menu_",
    ))

    # ── Feature callbacks (news, stubs) ───────────────────────────────────────
    app.add_handler(CallbackQueryHandler(callback_news, pattern="^feature_news$"))
    app.add_handler(CallbackQueryHandler(stub_premarket, pattern="^feature_premarket$"))
    app.add_handler(CallbackQueryHandler(stub_postmarket, pattern="^feature_postmarket$"))
    app.add_handler(CallbackQueryHandler(stub_script, pattern="^feature_script$"))
    app.add_handler(CallbackQueryHandler(stub_brand, pattern="^feature_brand$"))
    app.add_handler(CallbackQueryHandler(stub_sales, pattern="^feature_sales$"))
    app.add_handler(CallbackQueryHandler(stub_property, pattern="^feature_property$"))
    app.add_handler(CallbackQueryHandler(stub_landlord, pattern="^feature_landlord$"))
    app.add_handler(CallbackQueryHandler(stub_checkin, pattern="^feature_checkin$"))

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
            webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}",
            allowed_updates=["message", "callback_query"],
        )
    else:
        logger.info("Starting in polling mode (local dev)...")
        app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()

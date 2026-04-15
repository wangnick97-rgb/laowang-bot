"""
老王工具箱 — Telegram Bot 入口
4板块架构: 创业财富 / 个人健康 / 个人成长 / 会员中心
"""
import logging

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
from services.scheduler import setup_scheduler

# ── 创业财富 handlers ────────────────────────────────────────────────────────
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
from bot.handlers.daily_poll import cmd_vote, callback_vote
from bot.handlers.wealth_static import show_portfolio, show_strategy, show_us_stock_guide, cmd_signal, show_autotrading

# ── 个人健康 handlers ────────────────────────────────────────────────────────
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

# ── 个人成长 handlers ────────────────────────────────────────────────────────
from bot.handlers.daily_cognition import build_handler as cognition_handler
from bot.handlers.decision_helper import build_handler as decision_handler
from bot.handlers.evening_review import build_handler as review_handler
from bot.handlers.text_optimizer import build_handler as text_opt_handler
from bot.handlers.biz_reply import build_handler as biz_reply_handler
from bot.handlers.script_polish import build_handler as script_polish_handler
from bot.handlers.daily_english import build_handler as english_handler
from bot.handlers.chinglish_fix import build_handler as chinglish_handler
from bot.handlers.biz_english import build_handler as biz_english_handler
from bot.handlers.daily_plan import build_handler as plan_handler
from bot.handlers.deep_work import build_handler as deep_work_handler
from bot.handlers.procrastination import build_handler as procrastination_handler
from bot.handlers.challenge_21day import entry as show_21day

# ── 会员中心 handlers ────────────────────────────────────────────────────────
from bot.handlers.daily_checkin import build_handler as checkin_handler, show_leaderboard, show_badges
from bot.handlers.points_shop import cmd_points, callback_redeem
from bot.handlers.consultation import build_handler as consult_handler
from bot.handlers.referral import cmd_invite
from bot.handlers.join import callback_join
from bot.handlers.admin import cmd_addmember, cmd_removemember, cmd_members, cmd_stats, cmd_h5token
from bot.handlers.member_center import show_streaks, show_membership_info, callback_invite_redirect
from bot.handlers.activation import cmd_gencode, cmd_activate, cmd_codes
from bot.handlers.group_chat import track_group_message, cmd_groupstats, cmd_mychat
from bot.middleware import group_command_redirect

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("start", "开始 / 主菜单"),
    BotCommand("menu", "返回主菜单"),
    # 创业财富
    BotCommand("news", "📰 今日简报"),
    BotCommand("trade", "📈 交易复盘"),
    BotCommand("topic", "🔥 爆款选题"),
    # 个人健康
    BotCommand("workout", "🏋️ 今日训练"),
    BotCommand("meal", "🍽️ 今日食谱"),
    BotCommand("gym", "🏃 健身打卡"),
    BotCommand("health", "❤️ 健康打卡"),
    # 个人成长
    BotCommand("cognition", "💡 今日认知"),
    BotCommand("review", "🌙 晚间复盘"),
    BotCommand("english", "📝 今日英语"),
    BotCommand("plan", "📋 今日计划"),
    BotCommand("focus", "🔥 深度工作"),
    # 会员中心
    BotCommand("checkin", "✅ 每日签到"),
    BotCommand("points", "🪙 我的积分"),
    BotCommand("invite", "🎁 邀请好友"),
    BotCommand("activate", "🔑 激活会员"),
    BotCommand("cancel", "取消当前操作"),
    BotCommand("help", "使用说明"),
]


async def cmd_help(update, context):
    await update.message.reply_text(
        "*老王工具箱 — 使用说明*\n\n"
        "💰 *创业财富*\n"
        "/news — 今日财经简报\n"
        "/trade — 交易复盘\n"
        "/topic — 爆款选题\n\n"
        "💪 *个人健康*\n"
        "/workout — AI训练计划\n"
        "/meal — AI食谱\n"
        "/gym — 健身打卡\n"
        "/health — 健康打卡\n\n"
        "🧠 *个人成长*\n"
        "/cognition — 今日认知训练\n"
        "/review — 晚间复盘\n"
        "/english — 今日英语升级\n"
        "/plan — 今日计划\n\n"
        "👤 *会员中心*\n"
        "/checkin — 每日签到\n"
        "/points — 我的积分\n"
        "/invite — 邀请好友\n\n"
        "/menu — 返回主菜单\n"
        "/cancel — 取消当前操作\n\n"
        "有问题联系 @scorpia2004",
        parse_mode="Markdown",
    )


def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # ── 群聊命令拦截（最高优先级，group=-1）─────────────────────────────────
    # 在群里使用命令时，提示用户去私聊，保护隐私
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.COMMAND,
        group_command_redirect,
    ), group=-1)

    # ── Core commands ────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("invite", cmd_invite))
    app.add_handler(CommandHandler("points", cmd_points))
    app.add_handler(CommandHandler("vote", cmd_vote))
    app.add_handler(CommandHandler("badges", lambda u, c: show_badges(u, c)))

    # ── Activation codes ─────────────────────────────────────────────────────
    app.add_handler(CommandHandler("activate", cmd_activate))
    app.add_handler(CommandHandler("gencode", cmd_gencode))
    app.add_handler(CommandHandler("codes", cmd_codes))

    # ── Admin commands ───────────────────────────────────────────────────────
    app.add_handler(CommandHandler("addmember", cmd_addmember))
    app.add_handler(CommandHandler("removemember", cmd_removemember))
    app.add_handler(CommandHandler("members", cmd_members))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("signal", cmd_signal))
    app.add_handler(CommandHandler("groupstats", cmd_groupstats))
    app.add_handler(CommandHandler("mychat", cmd_mychat))
    app.add_handler(CommandHandler("h5token", cmd_h5token))

    # ── ConversationHandlers (before generic CallbackQueryHandlers) ────────
    # 创业财富
    app.add_handler(trade_handler())
    app.add_handler(topic_handler())
    app.add_handler(script_handler())
    app.add_handler(brand_handler())
    app.add_handler(sales_handler())
    app.add_handler(property_handler())
    app.add_handler(landlord_handler())
    # 个人健康
    app.add_handler(protein_handler())
    app.add_handler(calorie_handler())
    app.add_handler(gym_handler())
    app.add_handler(health_checkin_handler())
    app.add_handler(workout_handler())
    app.add_handler(meal_handler())
    app.add_handler(calorie_log_handler())
    app.add_handler(team_handler())
    # 个人成长
    app.add_handler(cognition_handler())
    app.add_handler(decision_handler())
    app.add_handler(review_handler())
    app.add_handler(text_opt_handler())
    app.add_handler(biz_reply_handler())
    app.add_handler(script_polish_handler())
    app.add_handler(english_handler())
    app.add_handler(chinglish_handler())
    app.add_handler(biz_english_handler())
    app.add_handler(plan_handler())
    app.add_handler(deep_work_handler())
    app.add_handler(procrastination_handler())
    # 会员中心
    app.add_handler(checkin_handler())
    app.add_handler(consult_handler())

    # ── Menu navigation ──────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(handle_menu_navigation, pattern="^menu_"))

    # ── 创业财富 callbacks ───────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(callback_news, pattern="^feature_news$"))
    app.add_handler(CallbackQueryHandler(callback_premarket, pattern="^feature_premarket$"))
    app.add_handler(CallbackQueryHandler(callback_postmarket, pattern="^feature_postmarket$"))
    app.add_handler(CallbackQueryHandler(callback_vote, pattern="^vote_\\d+$"))
    app.add_handler(CallbackQueryHandler(show_portfolio, pattern="^feature_wang_portfolio$"))
    app.add_handler(CallbackQueryHandler(show_strategy, pattern="^feature_wang_strategy$"))
    app.add_handler(CallbackQueryHandler(show_us_stock_guide, pattern="^feature_us_stock_guide$"))
    app.add_handler(CallbackQueryHandler(show_autotrading, pattern="^feature_autotrading$"))
    app.add_handler(CallbackQueryHandler(cmd_vote, pattern="^feature_vote$"))

    # ── 个人健康 callbacks ───────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(show_snacks, pattern="^feature_snacks$"))
    app.add_handler(CallbackQueryHandler(show_supplements, pattern="^feature_supplements$"))
    app.add_handler(CallbackQueryHandler(show_health_rank, pattern="^feature_health_rank$"))
    app.add_handler(CallbackQueryHandler(show_plan_menu, pattern="^feature_wangplan$"))
    app.add_handler(CallbackQueryHandler(show_plan_detail, pattern="^wplan_"))
    app.add_handler(CallbackQueryHandler(show_challenges, pattern="^feature_challenge$"))
    app.add_handler(CallbackQueryHandler(callback_join_challenge, pattern="^join_challenge_"))
    app.add_handler(CallbackQueryHandler(show_team, pattern="^feature_team$"))
    app.add_handler(CallbackQueryHandler(show_team_rank, pattern="^team_rank$"))
    app.add_handler(CallbackQueryHandler(show_report, pattern="^feature_report$"))
    app.add_handler(CallbackQueryHandler(send_share_text, pattern="^copy_report$"))

    # ── 个人成长 callbacks ───────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(show_21day, pattern="^feature_21day$"))

    # ── 会员中心 callbacks ───────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(callback_join, pattern="^join_member$"))
    app.add_handler(CallbackQueryHandler(show_leaderboard, pattern="^checkin_leaderboard$"))
    app.add_handler(CallbackQueryHandler(callback_redeem, pattern="^redeem_"))
    app.add_handler(CallbackQueryHandler(show_badges, pattern="^my_badges$"))
    app.add_handler(CallbackQueryHandler(show_streaks, pattern="^feature_streaks$"))
    app.add_handler(CallbackQueryHandler(show_membership_info, pattern="^feature_membership_info$"))
    app.add_handler(CallbackQueryHandler(callback_invite_redirect, pattern="^feature_invite$"))
    app.add_handler(CallbackQueryHandler(cmd_points, pattern="^feature_points$"))
    app.add_handler(CallbackQueryHandler(
        lambda u, c: cmd_activate(u, c), pattern="^feature_activate$"
    ))

    # ── Command shortcuts ────────────────────────────────────────────────────
    app.add_handler(CommandHandler("challenge", show_challenges))
    app.add_handler(CommandHandler("team", show_team))
    app.add_handler(CommandHandler("report", show_report))

    # ── 群聊消息追踪（必须放最后，只追踪群组消息）──────────────────────────
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        track_group_message,
    ))

    return app


async def post_init(app: Application):
    await app.bot.set_my_commands(BOT_COMMANDS)
    setup_scheduler(app.bot)
    logger.info("Bot initialized. Mode: %s", BOT_MODE)


def main():
    """Standalone entry point (local dev polling mode)."""
    app = build_app()

    if BOT_MODE == "webhook" and WEBHOOK_URL:
        # In production, use webapp/api.py (FastAPI + uvicorn) instead
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TELEGRAM_BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}",
            allowed_updates=["message", "callback_query", "my_chat_member"],
        )
    else:
        logger.info("Starting in polling mode (local dev)...")
        app.run_polling(allowed_updates=["message", "callback_query", "my_chat_member"])


if __name__ == "__main__":
    main()

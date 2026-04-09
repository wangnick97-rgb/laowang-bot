"""
Feature: 商务回复助手
Flow: entry → ASK_SCENARIO → ASK_MESSAGE → generate → END
User picks scenario, pastes the other party's message, gets 3 tone versions.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership, require_usage_quota
from services.claude_client import call_claude

ASK_SCENARIO, ASK_MESSAGE = range(2)
_KEY = "biz_reply"

_SCENARIOS = {
    "biz_sc_reject": "拒绝",
    "biz_sc_collect": "催款",
    "biz_sc_negotiate": "谈判",
    "biz_sc_apologize": "道歉",
    "biz_sc_invite": "邀约",
    "biz_sc_report": "上级汇报",
}

def _scenario_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚫 拒绝", callback_data="biz_sc_reject"),
            InlineKeyboardButton("💰 催款", callback_data="biz_sc_collect"),
            InlineKeyboardButton("🤝 谈判", callback_data="biz_sc_negotiate"),
        ],
        [
            InlineKeyboardButton("🙏 道歉", callback_data="biz_sc_apologize"),
            InlineKeyboardButton("📨 邀约", callback_data="biz_sc_invite"),
            InlineKeyboardButton("📊 上级汇报", callback_data="biz_sc_report"),
        ],
        [InlineKeyboardButton("❌ 取消", callback_data="cancel_biz_reply")],
    ])

def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_biz_reply")]])

def _done_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 再回复一条", callback_data="feature_biz_reply"),
        InlineKeyboardButton("← 表达系统", callback_data="menu_expression"),
    ]])


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    reply = query.message.reply_text if query else update.message.reply_text
    if query:
        await query.answer()
    await reply(
        "💼 *商务回复助手*\n\n"
        "选择你要回复的场景，我会帮你生成 3 种语气版本：\n"
        "• 直接版 — 高效、不兜圈子\n"
        "• 委婉版 — 礼貌、留面子\n"
        "• 留余地版 — 灵活、不关门\n\n"
        "请选择场景 👇",
        parse_mode="Markdown",
        reply_markup=_scenario_kb(),
    )
    return ASK_SCENARIO


async def pick_scenario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    scenario_key = q.data
    scenario_label = _SCENARIOS.get(scenario_key, "商务")
    context.user_data["biz_scenario"] = scenario_label
    await q.edit_message_text(
        f"💼 场景：*{scenario_label}*\n\n"
        "请把对方发来的消息粘贴给我，我来帮你回复 👇",
        parse_mode="Markdown",
    )
    await q.message.reply_text("等待你的消息...", reply_markup=_cancel_kb())
    return ASK_MESSAGE


@require_usage_quota
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("💼 正在生成 3 种回复方案，稍等...")
    scenario = context.user_data.get("biz_scenario", "商务")
    user_text = update.message.text.strip()
    prompt = (
        f"你是一位专业的商务沟通顾问。场景：{scenario}。\n\n"
        "对方发来的消息如下：\n"
        f"「{user_text}」\n\n"
        "请生成 3 种不同语气的回复：\n"
        "1. *直接版* — 高效、不兜圈子，适合关系较近或事情紧急\n"
        "2. *委婉版* — 礼貌、留面子，适合一般商务关系\n"
        "3. *留余地版* — 灵活、不关门，适合还想保持合作可能\n\n"
        "每个版本后附一句使用建议。"
    )
    result = await call_claude(_KEY, prompt,
                               user_id=update.effective_user.id, max_tokens=1500)
    await update.message.reply_text(result, parse_mode="Markdown", reply_markup=_done_kb())
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q:
        await q.answer()
        await q.edit_message_text("已取消。发送 /menu 返回主菜单。")
    else:
        await update.message.reply_text("已取消。发送 /menu 返回主菜单。")
    return ConversationHandler.END


def build_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("reply", entry),
            CallbackQueryHandler(entry, pattern="^feature_biz_reply$"),
        ],
        states={
            ASK_SCENARIO: [
                CallbackQueryHandler(pick_scenario, pattern="^biz_sc_"),
            ],
            ASK_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, generate),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_biz_reply$"),
        ],
        conversation_timeout=300,
        per_user=True, per_chat=True, allow_reentry=True,
    )

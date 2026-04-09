"""
Feature: 商务英语对话
Flow: entry → ASK_BIZ_SCENARIO (callback buttons) → Claude generates dialogue + vocabulary → END
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    CallbackQueryHandler, filters,
)
from bot.middleware import require_membership, require_usage_quota
from services.claude_client import call_claude

ASK_BIZ_SCENARIO = 0
_KEY = "biz_english"

_SCENARIOS = {
    "beng_email": {"label": "📧 商务邮件", "prompt": "商务邮件场景（如：回复客户询价、跟进项目进展、请求会议时间等）"},
    "beng_meeting": {"label": "🏢 会议讨论", "prompt": "英文会议场景（如：提出建议、表达反对意见、总结行动项等）"},
    "beng_pitch": {"label": "🎤 Pitch/演讲", "prompt": "Pitch 或商务演讲场景（如：介绍产品、吸引投资人、汇报成果等）"},
    "beng_social": {"label": "🤝 社交寒暄", "prompt": "商务社交场景（如：networking、商务晚宴、初次见面寒暄等）"},
    "beng_interview": {"label": "💼 求职面试", "prompt": "英文面试场景（如：自我介绍、回答行为面试题、薪资谈判等）"},
}


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_biz_eng")]])


def _scenario_kb():
    buttons = [[InlineKeyboardButton(s["label"], callback_data=k)] for k, s in _SCENARIOS.items()]
    buttons.append([InlineKeyboardButton("❌ 取消", callback_data="cancel_biz_eng")])
    return InlineKeyboardMarkup(buttons)


def _done_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 换个场景", callback_data="feature_biz_english"),
         InlineKeyboardButton("← 英语系统", callback_data="menu_english")],
        [InlineKeyboardButton("← 个人成长", callback_data="menu_growth")],
    ])


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    reply = query.message.reply_text if query else update.message.reply_text
    if query:
        await query.answer()
    await reply(
        "💬 *商务英语对话练习*\n\n"
        "选择一个场景，我来生成一段地道的商务对话 + 核心词汇表。\n\n"
        "选择你想练习的场景 👇",
        parse_mode="Markdown",
        reply_markup=_scenario_kb(),
    )
    return ASK_BIZ_SCENARIO


@require_usage_quota
async def handle_scenario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    scenario_key = query.data
    scenario = _SCENARIOS.get(scenario_key)
    if not scenario:
        await query.message.reply_text("未知场景，请重新选择。", reply_markup=_scenario_kb())
        return ASK_BIZ_SCENARIO

    user_id = update.effective_user.id

    prompt = (
        f"请生成一段{scenario['prompt']}的英文对话练习。\n\n"
        f"要求：\n"
        f"1. 写一段 6-10 轮的对话（双方各 3-5 句），标注角色\n"
        f"2. 对话要自然地道，体现真实商务场景\n"
        f"3. 对话后列出 *核心词汇表*（5-8 个），每个词给出：英文、中文释义、例句\n"
        f"4. 最后给 2-3 个 *实用句型*，可以直接套用\n\n"
        f"格式清晰，用中文解释，英文部分保持英文。"
    )

    await query.message.reply_text(f"💬 正在生成{scenario['label']}对话练习...")
    result = await call_claude(_KEY, prompt, user_id=user_id, max_tokens=1200)
    await query.message.reply_text(result, parse_mode="Markdown", reply_markup=_done_kb())
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
            CommandHandler("bizenglish", entry),
            CallbackQueryHandler(entry, pattern="^feature_biz_english$"),
        ],
        states={
            ASK_BIZ_SCENARIO: [
                CallbackQueryHandler(handle_scenario, pattern="^beng_(email|meeting|pitch|social|interview)$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_biz_eng$"),
        ],
        conversation_timeout=180,
        per_user=True, per_chat=True, allow_reentry=True,
    )

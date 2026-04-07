"""
Feature: 交易复盘 (Trade Review)
Multi-step ConversationHandler — canonical template for all multi-step features.

Flow:
  Entry → ASK_INSTRUMENT → ASK_ENTRY_EXIT → ASK_EMOTION → ASK_OUTCOME → [Claude] → END
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from bot.middleware import require_membership, require_usage_quota
from services.claude_client import call_claude

# ── Conversation states ────────────────────────────────────────────────────────
ASK_INSTRUMENT = 0
ASK_ENTRY_EXIT = 1
ASK_EMOTION = 2
ASK_OUTCOME = 3

FEATURE_KEY = "trade_review"


def _cancel_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ 取消", callback_data="cancel_trade")
    ]])


def _back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📈 再复盘一笔", callback_data="feature_trade"),
        InlineKeyboardButton("← 主菜单", callback_data="menu_main"),
    ]])


# ── Entry point ────────────────────────────────────────────────────────────────

@require_membership
async def entry_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry via /trade command or feature_trade callback."""
    query = update.callback_query
    if query:
        await query.answer()
        reply_fn = query.message.reply_text
    else:
        reply_fn = update.message.reply_text

    context.user_data["trade"] = {}
    await reply_fn(
        "📈 *交易复盘*\n\n"
        "我会帮你分析这笔交易的纪律性和情绪，给出改进建议。\n\n"
        "*第 1 步：交易品种*\n"
        "请告诉我你交易的是什么？\n"
        "例如：AAPL、比特币、NVDA 期权",
        parse_mode="Markdown",
        reply_markup=_cancel_button(),
    )
    return ASK_INSTRUMENT


# ── Step handlers ──────────────────────────────────────────────────────────────

async def ask_entry_exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["trade"]["instrument"] = update.message.text.strip()
    await update.message.reply_text(
        "✅ 记录了。\n\n"
        "*第 2 步：入场和出场*\n"
        "请告诉我你的入场价/时间和出场价/时间。\n"
        "例如：入场 $182.50（周二下午2点），出场 $179.20（当天收盘前）",
        parse_mode="Markdown",
        reply_markup=_cancel_button(),
    )
    return ASK_ENTRY_EXIT


async def ask_emotion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["trade"]["entry_exit"] = update.message.text.strip()
    await update.message.reply_text(
        "✅ 记录了。\n\n"
        "*第 3 步：当时的情绪和想法*\n"
        "进场时你在想什么？有没有感到 FOMO、焦虑、或者很有把握？\n"
        "出场时呢？",
        parse_mode="Markdown",
        reply_markup=_cancel_button(),
    )
    return ASK_EMOTION


async def ask_outcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["trade"]["emotion"] = update.message.text.strip()
    await update.message.reply_text(
        "✅ 记录了。\n\n"
        "*第 4 步：最终结果*\n"
        "这笔交易盈利还是亏损？大概多少金额或百分比？\n"
        "（也可以说『盈亏平衡』或者『还在持仓』）",
        parse_mode="Markdown",
        reply_markup=_cancel_button(),
    )
    return ASK_OUTCOME


@require_usage_quota
async def analyze_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["trade"]["outcome"] = update.message.text.strip()
    data = context.user_data["trade"]

    await update.message.reply_text("🔍 正在分析你的交易，请稍候...")

    user_message = (
        f"品种：{data['instrument']}\n"
        f"入场/出场：{data['entry_exit']}\n"
        f"当时情绪：{data['emotion']}\n"
        f"最终结果：{data['outcome']}"
    )

    result = await call_claude(
        FEATURE_KEY,
        user_message,
        user_id=update.effective_user.id,
        max_tokens=700,
    )

    await update.message.reply_text(
        result,
        parse_mode="Markdown",
        reply_markup=_back_button(),
    )

    context.user_data.pop("trade", None)
    return ConversationHandler.END


# ── Cancel ─────────────────────────────────────────────────────────────────────

async def cancel_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("已取消复盘。发送 /menu 返回主菜单。")
    else:
        await update.message.reply_text("已取消复盘。发送 /menu 返回主菜单。")
    context.user_data.pop("trade", None)
    return ConversationHandler.END


# ── ConversationHandler factory ────────────────────────────────────────────────

def build_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("trade", entry_trade),
            CallbackQueryHandler(entry_trade, pattern="^feature_trade$"),
        ],
        states={
            ASK_INSTRUMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_entry_exit)],
            ASK_ENTRY_EXIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_emotion)],
            ASK_EMOTION:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_outcome)],
            ASK_OUTCOME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_trade)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_trade),
            CommandHandler("menu", cancel_trade),
            CallbackQueryHandler(cancel_trade, pattern="^cancel_trade$"),
        ],
        conversation_timeout=300,   # 5 minutes idle = auto-cancel
        per_user=True,
        per_chat=True,
        allow_reentry=True,
    )

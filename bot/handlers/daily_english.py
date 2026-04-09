"""
Feature: 今日英语升级
Flow: entry (show daily expression) → ASK_PRACTICE (user writes sentence) → Claude evaluates → END
Awards 3 points for practicing.
"""
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership, require_usage_quota
from services.claude_client import call_claude
from db.client import get_client

ASK_PRACTICE = 0
_KEY = "daily_english"

_EXPRESSIONS = [
    {"phrase": "push back", "wrong": "I don't agree with this idea", "right": "I'd like to push back on this", "meaning": "礼貌地表达不同意见", "examples": ["I need to push back on the timeline.", "She pushed back on the budget proposal."]},
    {"phrase": "circle back", "wrong": "Let's discuss later", "right": "Let me circle back on this", "meaning": "稍后再回头讨论某事", "examples": ["Can we circle back on the pricing?", "I'll circle back with you after the meeting."]},
    {"phrase": "move the needle", "wrong": "Make some progress", "right": "This will really move the needle", "meaning": "产生显著的影响或进展", "examples": ["We need campaigns that move the needle.", "That feature didn't move the needle on retention."]},
    {"phrase": "on the same page", "wrong": "We think the same", "right": "Let's make sure we're on the same page", "meaning": "确保大家理解一致", "examples": ["Are we on the same page about the deadline?", "I want to get on the same page before the launch."]},
    {"phrase": "low-hanging fruit", "wrong": "Easy things to do", "right": "Let's start with the low-hanging fruit", "meaning": "容易实现的目标或任务", "examples": ["Fixing the FAQ page is low-hanging fruit.", "We should tackle the low-hanging fruit first."]},
    {"phrase": "take it offline", "wrong": "Let's talk privately", "right": "Let's take this offline", "meaning": "会后单独讨论（不占用大家时间）", "examples": ["This is getting detailed — let's take it offline.", "Can we take this offline and sync later?"]},
    {"phrase": "bandwidth", "wrong": "I don't have time", "right": "I don't have the bandwidth right now", "meaning": "当前的时间/精力余量", "examples": ["Do you have bandwidth to take on this project?", "My bandwidth is pretty limited this quarter."]},
    {"phrase": "deep dive", "wrong": "Study carefully", "right": "Let's do a deep dive into the data", "meaning": "深入研究或分析某个话题", "examples": ["We need a deep dive on customer churn.", "I did a deep dive into the competitor's strategy."]},
    {"phrase": "run with it", "wrong": "You can do it", "right": "Great idea — run with it", "meaning": "放手去做，全权负责推进", "examples": ["If you feel strongly about this, run with it.", "The CEO liked the pitch and told us to run with it."]},
    {"phrase": "double down", "wrong": "Try harder", "right": "We need to double down on content marketing", "meaning": "加倍投入某个方向", "examples": ["They doubled down on short-form video.", "It's time to double down on what's working."]},
    {"phrase": "pivot", "wrong": "Change direction", "right": "We decided to pivot our strategy", "meaning": "战略性地调整方向", "examples": ["The startup pivoted from B2C to B2B.", "If the data says so, we should pivot."]},
    {"phrase": "touch base", "wrong": "Let's contact each other", "right": "I just wanted to touch base on the project", "meaning": "简短沟通/确认进展", "examples": ["Let's touch base next Monday.", "I'm touching base to see if you need anything."]},
    {"phrase": "leverage", "wrong": "Use something", "right": "We should leverage our existing customer base", "meaning": "充分利用（资源/优势）", "examples": ["Leverage your network for introductions.", "We can leverage AI to automate this process."]},
    {"phrase": "actionable", "wrong": "Can be done", "right": "We need actionable insights from this report", "meaning": "可以立即付诸行动的", "examples": ["Give me something actionable, not just data.", "The feedback wasn't actionable enough."]},
    {"phrase": "align", "wrong": "We need to agree", "right": "Let's align on priorities before the sprint", "meaning": "统一方向/达成共识", "examples": ["We need to align the team on the roadmap.", "Are sales and marketing aligned on messaging?"]},
    {"phrase": "unpack", "wrong": "Explain in detail", "right": "Let me unpack that for you", "meaning": "拆解分析复杂的内容", "examples": ["Can you unpack what the client meant?", "Let's unpack the quarterly results."]},
    {"phrase": "buy-in", "wrong": "Agreement from others", "right": "We need buy-in from leadership", "meaning": "获得关键人物的支持/认可", "examples": ["Without buy-in from the board, this won't fly.", "How do we get buy-in from the sales team?"]},
    {"phrase": "table this", "wrong": "Let's stop talking about this", "right": "Let's table this for now and revisit next week", "meaning": "暂时搁置，以后再议", "examples": ["We should table this until we have more data.", "The committee voted to table the proposal."]},
    {"phrase": "bottleneck", "wrong": "The problem part", "right": "Engineering is the bottleneck right now", "meaning": "阻碍流程的瓶颈环节", "examples": ["What's the bottleneck in our hiring process?", "Approvals are the biggest bottleneck."]},
    {"phrase": "heads up", "wrong": "I want to tell you something", "right": "Just a heads up — the meeting moved to 3 PM", "meaning": "提前告知/预警", "examples": ["Heads up, the client might push back on pricing.", "Thanks for the heads up about the delay."]},
    {"phrase": "scale", "wrong": "Make it bigger", "right": "How do we scale this process?", "meaning": "规模化扩展（业务/流程）", "examples": ["This works manually, but it won't scale.", "We need to figure out how to scale the team."]},
    {"phrase": "ownership", "wrong": "Who is responsible", "right": "I'll take ownership of this deliverable", "meaning": "主动承担责任", "examples": ["She took full ownership of the launch.", "We need clear ownership on every task."]},
    {"phrase": "flag", "wrong": "I want to mention a problem", "right": "I want to flag a potential risk", "meaning": "标记/提醒注意某个问题", "examples": ["Let me flag this before we proceed.", "She flagged a compliance issue early on."]},
    {"phrase": "sync up", "wrong": "Let's have a meeting", "right": "Can we sync up for 15 minutes?", "meaning": "快速碰头对齐信息", "examples": ["Let's sync up before the client call.", "I need to sync up with the design team."]},
    {"phrase": "wrap up", "wrong": "Let's finish", "right": "Let's wrap up and share the action items", "meaning": "收尾并总结要点", "examples": ["We should wrap up — we're over time.", "To wrap up, here are the three key takeaways."]},
]


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_eng")]])


def _done_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 再练一次", callback_data="feature_daily_english"),
         InlineKeyboardButton("← 英语系统", callback_data="menu_english")],
        [InlineKeyboardButton("← 个人成长", callback_data="menu_growth")],
    ])


def _get_today_expression() -> dict:
    idx = date.today().toordinal() % len(_EXPRESSIONS)
    return _EXPRESSIONS[idx]


@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    reply = query.message.reply_text if query else update.message.reply_text
    if query:
        await query.answer()

    expr = _get_today_expression()
    examples_text = "\n".join(f"  • _{ex}_" for ex in expr["examples"])

    await reply(
        f"📝 *今日英语升级*\n\n"
        f"🔑 今日表达：*{expr['phrase']}*\n"
        f"📖 含义：{expr['meaning']}\n\n"
        f"❌ 中式说法：{expr['wrong']}\n"
        f"✅ 地道说法：{expr['right']}\n\n"
        f"💡 *例句*\n{examples_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✏️ *练习时间*\n"
        f"用 *{expr['phrase']}* 写一个句子，我来帮你点评 👇",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_PRACTICE


@require_usage_quota
async def evaluate_practice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    expr = _get_today_expression()
    user_sentence = update.message.text.strip()

    prompt = (
        f"用户正在练习英语表达 \"{expr['phrase']}\"（含义：{expr['meaning']}）。\n"
        f"用户写的句子：{user_sentence}\n\n"
        f"请你：\n"
        f"1. 判断用户是否正确使用了该表达\n"
        f"2. 如果有语法或用法问题，指出并纠正\n"
        f"3. 给出一个改进版本（如果需要）\n"
        f"4. 用一句话鼓励用户\n\n"
        f"用中文回复，英文部分保持英文。简洁有力。"
    )

    await update.message.reply_text("📝 正在点评你的句子...")
    result = await call_claude(_KEY, prompt, user_id=user_id, max_tokens=500)

    # Award 3 points for practicing
    db = get_client()
    user = db.table("users").select("points").eq("id", user_id).maybe_single().execute()
    new_points = ((user.data or {}).get("points", 0) or 0) + 3
    db.table("users").update({"points": new_points}).eq("id", user_id).execute()

    await update.message.reply_text(
        f"{result}\n\n🪙 +3 积分（练习奖励）",
        parse_mode="Markdown",
        reply_markup=_done_kb(),
    )
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
            CommandHandler("english", entry),
            CallbackQueryHandler(entry, pattern="^feature_daily_english$"),
        ],
        states={ASK_PRACTICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, evaluate_practice)]},
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_eng$"),
        ],
        conversation_timeout=300,
        per_user=True, per_chat=True, allow_reentry=True,
    )

"""
Feature: 今日认知 (Daily Cognition)
每天一个认知偏差/心智模型话题 + 思考题 → 用户回答 → Claude 点评反馈 → +5 积分
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

ASK_REFLECTION = 0
_KEY = "daily_cognition"

# ── 20 个认知话题 ─────────────────────────────────────────────────────────────

_TOPICS = [
    {
        "title": "确认偏误 (Confirmation Bias)",
        "desc": "人倾向于只关注支持自己已有观点的信息，忽略或贬低反面证据。",
        "question": "回忆一下，最近你做一个决定时，有没有只看了支持你立场的信息，而忽略了反面证据？具体是什么？",
    },
    {
        "title": "沉没成本谬误 (Sunk Cost Fallacy)",
        "desc": "因为已经投入了时间/金钱/精力，所以不愿放弃，即使继续下去明显不划算。",
        "question": "你现在生活中有没有一件事，你知道该放弃，但因为已经投入太多而不舍得？说说看。",
    },
    {
        "title": "锚定效应 (Anchoring Effect)",
        "desc": "第一个接收到的数字或信息会成为「锚」，后续判断被它拉偏。",
        "question": "你最近买东西或谈价格时，有没有被「原价」或「别人给的第一个数字」影响了判断？",
    },
    {
        "title": "幸存者偏差 (Survivorship Bias)",
        "desc": "只看到成功案例，忽略了大量失败案例，导致对成功概率的估计严重偏高。",
        "question": "你有没有因为看到某个人成功了，就觉得「我也能行」，而忽略了背后成千上万失败者？",
    },
    {
        "title": "达克效应 (Dunning-Kruger Effect)",
        "desc": "能力不足的人往往高估自己，能力强的人反而容易低估自己。",
        "question": "你有没有某个领域，以前觉得自己很懂，后来发现自己当时根本不懂？是什么让你意识到的？",
    },
    {
        "title": "损失厌恶 (Loss Aversion)",
        "desc": "失去100元的痛苦大约是得到100元快乐的2倍。人天然更怕亏。",
        "question": "你有没有因为害怕失去某个东西（机会/钱/关系），做了一个事后看来不理性的决定？",
    },
    {
        "title": "可得性偏差 (Availability Bias)",
        "desc": "越容易想到的事，我们越觉得它常见。飞机失事新闻多了，你就觉得飞机不安全。",
        "question": "你有没有因为身边某个人的经历或最近看到的新闻，高估了某件事发生的概率？",
    },
    {
        "title": "第一性原理 (First Principles Thinking)",
        "desc": "把问题拆解到最基本的事实，从零开始推理，不被类比和经验限制。",
        "question": "你工作或生活中有没有一件事，大家都觉得「只能这么做」，但如果从根本上重新想，其实有更好的方案？",
    },
    {
        "title": "逆向思维 (Inversion)",
        "desc": "与其想「怎么成功」，不如想「怎么一定会失败」，然后避开那些坑。",
        "question": "如果你想让自己目前最重要的目标一定失败，你会怎么做？（反着想，就知道该避免什么了。）",
    },
    {
        "title": "二阶思维 (Second-Order Thinking)",
        "desc": "不只想「这个决定的直接结果是什么」，还要想「这个结果会带来什么后果」。",
        "question": "你最近做的一个决定，它的直接结果你想过了，但它的「后果的后果」你想过吗？试着想一下。",
    },
    {
        "title": "能力圈 (Circle of Competence)",
        "desc": "巴菲特的核心理念：知道自己懂什么、不懂什么，只在懂的范围内下注。",
        "question": "诚实地说，你目前赚钱或做决策所依赖的领域，你真的懂到可以跑赢大多数人吗？你的能力圈边界在哪？",
    },
    {
        "title": "奥卡姆剃刀 (Occam's Razor)",
        "desc": "如无必要，勿增实体。最简单的解释往往最接近真相。",
        "question": "你有没有把一件本来简单的事想复杂了？为什么你会「过度思考」这件事？",
    },
    {
        "title": "从众效应 (Bandwagon Effect)",
        "desc": "当大多数人都在做某件事时，我们不自觉地跟随，觉得「这么多人不会都错」。",
        "question": "你最近有没有一个决定是因为「大家都在做」所以才做的？如果没有别人的影响，你还会做吗？",
    },
    {
        "title": "禀赋效应 (Endowment Effect)",
        "desc": "拥有一件东西后，你会高估它的价值。你的车、你的项目、你的想法，在你眼里都比实际更值钱。",
        "question": "你有没有对自己的某个项目/想法/物品赋予了过高的评价？如果是别人的，你还会觉得它那么好吗？",
    },
    {
        "title": "框架效应 (Framing Effect)",
        "desc": "同一件事，用不同方式表述，会导致完全不同的决策。「手术成功率90%」比「手术失败率10%」让人安心得多。",
        "question": "你有没有被某个问题的「包装方式」影响了判断？换一种说法，你会做出不同的选择吗？",
    },
    {
        "title": "复利思维 (Compound Thinking)",
        "desc": "持续的微小改进会带来指数级回报。每天进步1%，一年后是37倍。关键在于「持续」。",
        "question": "你现在生活中有什么事在产生复利效应（越做越好，越积累越有价值）？有什么事在产生负复利？",
    },
    {
        "title": "帕累托法则 (80/20 Rule)",
        "desc": "80%的结果来自20%的投入。聪明人找到那个20%，然后all in。",
        "question": "你目前工作/生意中，哪20%的事情贡献了80%的收益？你花了多少精力在这20%上？",
    },
    {
        "title": "后视偏差 (Hindsight Bias)",
        "desc": "事后觉得「我早就知道了」。但你真的知道吗？还是因为已经知道了结果才这么觉得的？",
        "question": "你最近有没有对某件事觉得「早就预料到了」？诚实回忆一下，当时你真的那么确定吗？",
    },
    {
        "title": "规划谬误 (Planning Fallacy)",
        "desc": "人总是低估完成任务需要的时间、成本和精力。你说一周能做完的项目，大概率要两周。",
        "question": "你最近有没有一件事，比你预期花了多得多的时间或精力？为什么你当初的估算偏了？",
    },
    {
        "title": "机会成本 (Opportunity Cost)",
        "desc": "选择做A，就意味着放弃了做B/C/D的可能。真正的成本不是你付出了什么，而是你放弃了什么。",
        "question": "你目前花时间最多的一件事，它的机会成本是什么？你放弃的那些选项，值得吗？",
    },
]


def _get_topic(user_id: int) -> dict:
    idx = (user_id + date.today().toordinal()) % len(_TOPICS)
    return _TOPICS[idx]


def _cancel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ 取消", callback_data="cancel_daily_cognition")],
    ])


def _done_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💡 认知系统", callback_data="menu_cognition"),
         InlineKeyboardButton("← 主菜单", callback_data="menu_main")],
    ])


# ── Entry ─────────────────────────────────────────────────────────────────────

@require_membership
async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    reply = query.message.reply_text if query else update.message.reply_text
    if query:
        await query.answer()

    user_id = update.effective_user.id
    topic = _get_topic(user_id)

    await reply(
        f"💡 *今日认知训练*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📖 *{topic['title']}*\n\n"
        f"{topic['desc']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤔 *思考题*\n\n"
        f"*{topic['question']}*\n\n"
        f"写下你的想法，老王给你点评 👇",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_REFLECTION


# ── Respond ───────────────────────────────────────────────────────────────────

@require_usage_quota
async def respond(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    topic = _get_topic(user_id)
    user_input = (
        f"今日认知话题：{topic['title']}\n"
        f"话题说明：{topic['desc']}\n"
        f"思考题：{topic['question']}\n\n"
        f"用户回答：{update.message.text.strip()}"
    )

    await update.message.reply_text("🧠 老王正在看你的回答...")

    result = await call_claude(_KEY, user_input, user_id=user_id, max_tokens=600)

    # Award 5 points
    try:
        db = get_client()
        user = db.table("users").select("points").eq("id", user_id).maybe_single().execute()
        new_points = ((user.data or {}).get("points", 0) or 0) + 5
        db.table("users").update({"points": new_points}).eq("id", user_id).execute()
        points_text = f"\n\n🪙 +5 积分（认知训练奖励）"
    except Exception:
        points_text = ""

    await update.message.reply_text(
        result + points_text,
        parse_mode="Markdown",
        reply_markup=_done_kb(),
    )
    return ConversationHandler.END


# ── Cancel ────────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q:
        await q.answer()
        await q.edit_message_text("已取消。发送 /menu 返回主菜单。")
    else:
        await update.message.reply_text("已取消。发送 /menu 返回主菜单。")
    return ConversationHandler.END


# ── Handler factory ───────────────────────────────────────────────────────────

def build_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("cognition", entry),
            CallbackQueryHandler(entry, pattern="^feature_daily_cognition$"),
        ],
        states={
            ASK_REFLECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, respond)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_daily_cognition$"),
        ],
        conversation_timeout=300,
        per_user=True,
        per_chat=True,
        allow_reentry=True,
    )

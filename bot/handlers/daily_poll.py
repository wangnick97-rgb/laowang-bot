"""
Feature: 每日投票
每天一道投资/创业/认知话题投票，投票后可以看到其他人的选择分布。
"""
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.client import get_client

# 每日话题池
_POLLS = [
    {
        "q": "如果只能选一个副业，你会选？",
        "opts": ["📊 美股投资", "🏠 Airbnb", "✍️ 自媒体", "💻 AI工具开发"],
    },
    {
        "q": "你认为 2024-2025 最大的财富机会在哪？",
        "opts": ["🤖 AI 应用", "🏠 房地产", "📈 美股", "🎯 个人IP"],
    },
    {
        "q": "你更倾向哪种投资风格？",
        "opts": ["🐢 长期持有", "🐇 短线波段", "📊 量化策略", "🎲 跟着感觉"],
    },
    {
        "q": "你目前最大的瓶颈是？",
        "opts": ["💡 不知道做什么", "⚡ 知道但执行力差", "💰 缺启动资金", "👥 缺人脉资源"],
    },
    {
        "q": "做内容最难的是什么？",
        "opts": ["📝 不知道发什么", "📸 拍摄剪辑太难", "😰 怕被人评价", "📊 没有数据反馈"],
    },
    {
        "q": "你愿意为知识付费吗？",
        "opts": ["✅ 经常买课", "🤔 偶尔看情况", "❌ 免费的够了", "📚 只买书不买课"],
    },
    {
        "q": "如果有 10 万闲钱，你会？",
        "opts": ["📈 全部投美股", "🏠 凑首付买房", "🚀 投自己创业", "🏦 存银行吃利息"],
    },
    {
        "q": "每天花最多时间在？",
        "opts": ["📱 刷社交媒体", "💼 本职工作", "📚 学习提升", "🎮 娱乐休闲"],
    },
    {
        "q": "你觉得赚到第一个 100 万最快的路径是？",
        "opts": ["💼 高薪打工", "📊 投资理财", "🚀 自己创业", "✍️ 自媒体变现"],
    },
    {
        "q": "AI 会取代你的工作吗？",
        "opts": ["😰 很有可能", "🤔 部分会", "💪 不可能", "🤖 我已经在用AI了"],
    },
    {
        "q": "做 Airbnb 你最担心什么？",
        "opts": ["💸 前期投入大", "📋 政策风险", "😤 遇到烂客人", "⏰ 太耗精力"],
    },
    {
        "q": "你理想的工作状态是？",
        "opts": ["🏖️ 全球旅居", "🏠 在家远程", "🏢 稳定上班", "🚀 自己当老板"],
    },
    {
        "q": "止损做得怎么样？",
        "opts": ["✅ 严格执行", "😅 偶尔犹豫", "❌ 总是舍不得", "🤷 没有止损概念"],
    },
    {
        "q": "你更信哪个？",
        "opts": ["📊 数据和技术面", "📰 基本面和新闻", "💬 大V的建议", "🎯 自己的直觉"],
    },
]


def _today_poll() -> dict:
    idx = date.today().toordinal() % len(_POLLS)
    return _POLLS[idx]


def _poll_key() -> str:
    return f"poll_{date.today().isoformat()}"


def _get_poll_results() -> dict:
    """获取今日投票结果 {option_index: count}"""
    db = get_client()
    key = _poll_key()
    try:
        result = (
            db.table("daily_polls")
            .select("option_index")
            .eq("poll_key", key)
            .execute()
        )
        counts = {}
        for r in (result.data or []):
            idx = r["option_index"]
            counts[idx] = counts.get(idx, 0) + 1
        return counts
    except Exception:
        return {}


def _has_voted(user_id: int) -> bool:
    db = get_client()
    key = _poll_key()
    try:
        result = (
            db.table("daily_polls")
            .select("id")
            .eq("poll_key", key)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result and result.data is not None
    except Exception:
        return False


def _cast_vote(user_id: int, option_index: int):
    db = get_client()
    key = _poll_key()
    try:
        db.table("daily_polls").insert({
            "poll_key": key,
            "user_id": user_id,
            "option_index": option_index,
        }).execute()
    except Exception:
        pass


def _build_vote_keyboard(poll: dict) -> InlineKeyboardMarkup:
    buttons = []
    for i, opt in enumerate(poll["opts"]):
        buttons.append([InlineKeyboardButton(opt, callback_data=f"vote_{i}")])
    buttons.append([InlineKeyboardButton("← 主菜单", callback_data="menu_main")])
    return InlineKeyboardMarkup(buttons)


def _format_results(poll: dict, counts: dict, user_vote: int = None) -> str:
    total = sum(counts.values()) or 1
    lines = [f"📊 *投票结果*\n\n*{poll['q']}*\n"]

    for i, opt in enumerate(poll["opts"]):
        count = counts.get(i, 0)
        pct = round(count / total * 100)
        bar_len = round(pct / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        marker = " 👈 你" if i == user_vote else ""
        lines.append(f"{opt}\n`{bar}` {pct}% ({count}票){marker}\n")

    lines.append(f"共 {total} 人参与投票")
    return "\n".join(lines)


async def cmd_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    poll = _today_poll()

    if _has_voted(user_id):
        counts = _get_poll_results()
        # Find user's vote
        db = get_client()
        try:
            r = db.table("daily_polls").select("option_index").eq("poll_key", _poll_key()).eq("user_id", user_id).maybe_single().execute()
            user_vote = r.data["option_index"] if r and r.data else None
        except Exception:
            user_vote = None

        await update.message.reply_text(
            _format_results(poll, counts, user_vote),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("← 主菜单", callback_data="menu_main"),
            ]]),
        )
        return

    await update.message.reply_text(
        f"🗳️ *每日一问*\n\n*{poll['q']}*\n\n投票后可以看到其他人的选择 👇",
        parse_mode="Markdown",
        reply_markup=_build_vote_keyboard(poll),
    )


async def callback_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    if _has_voted(user_id):
        await query.answer("你今天已经投过票了！", show_alert=True)
        return

    option_index = int(query.data.replace("vote_", ""))
    _cast_vote(user_id, option_index)

    poll = _today_poll()
    counts = _get_poll_results()

    await query.edit_message_text(
        _format_results(poll, counts, option_index),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🌱 去签到", callback_data="feature_checkin"),
            InlineKeyboardButton("← 主菜单", callback_data="menu_main"),
        ]]),
    )

"""
Feature: 挑战任务系统
查看活跃挑战 → 加入 → 自动追踪进度 → 完成领奖
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from bot.middleware import require_membership
from db.health import (
    get_active_challenges, get_user_all_challenges,
    join_challenge, get_user_challenge_progress,
)

_TYPE_EMOJI = {"weekly": "📅", "monthly": "🏆", "special": "⭐"}
_TYPE_NAME = {"weekly": "周挑战", "monthly": "月挑战", "special": "特别挑战"}


def _back_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
    ])


@require_membership
async def show_challenges(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    challenges = get_user_all_challenges(user_id)

    if not challenges:
        text = (
            "🎯 *挑战任务*\n\n"
            "暂时没有活跃的挑战任务。\n"
            "管理员会定期发布新挑战，敬请期待！"
        )
        reply = query.message.reply_text if query else update.message.reply_text
        await reply(text, parse_mode="Markdown", reply_markup=_back_kb())
        return

    lines = ["🎯 *挑战任务*\n"]

    # 按类型分组
    current_type = None
    for c in challenges:
        ctype = c.get("challenge_type", "weekly")
        if ctype != current_type:
            current_type = ctype
            emoji = _TYPE_EMOJI.get(ctype, "📅")
            name = _TYPE_NAME.get(ctype, "挑战")
            lines.append(f"\n{emoji} *{name}*\n")

        title = c.get("title", "挑战")
        target = c.get("target_value", 0)
        reward = c.get("reward_points", 0)
        progress = c.get("current_progress", 0)
        joined = c.get("joined", False)
        completed = c.get("completed", False)

        if completed:
            status = "✅ 已完成"
            bar = "▓" * 10
        elif joined:
            pct = min(progress / target, 1.0) if target > 0 else 0
            filled = round(pct * 10)
            bar = "▓" * filled + "░" * (10 - filled)
            status = f"{progress}/{target}"
        else:
            bar = "░" * 10
            status = "未参加"

        lines.append(
            f"  *{title}*\n"
            f"  {bar} {status}\n"
            f"  🎁 奖励: {reward}积分"
        )

    lines.append("\n💡 点击下方按钮加入挑战")

    # 生成加入按钮（只显示未加入的）
    buttons = []
    for c in challenges:
        if not c.get("joined") and not c.get("completed"):
            buttons.append([InlineKeyboardButton(
                f"✋ 加入: {c.get('title', '挑战')}",
                callback_data=f"join_challenge_{c['id']}",
            )])

    buttons.append([InlineKeyboardButton("🔄 刷新进度", callback_data="feature_challenge")])
    buttons.append([InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")])

    reply = query.message.reply_text if query else update.message.reply_text
    await reply(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def callback_join_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data  # join_challenge_123
    try:
        challenge_id = int(data.replace("join_challenge_", ""))
    except ValueError:
        return

    user_id = update.effective_user.id
    success = join_challenge(user_id, challenge_id)

    if success:
        await query.message.reply_text(
            "✅ *成功加入挑战！*\n\n"
            "每次你完成相关打卡，进度会自动更新。\n"
            "加油！💪",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 查看进度", callback_data="feature_challenge")],
                [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
            ]),
        )
    else:
        await query.message.reply_text(
            "你已经加入了这个挑战，或挑战不存在。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 查看进度", callback_data="feature_challenge")],
            ]),
        )

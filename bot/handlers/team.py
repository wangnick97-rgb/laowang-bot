"""
Feature: 组队挑战
创建/加入战队 → 查看成员 → 战队排行榜
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
from bot.middleware import require_membership
from db.health import (
    create_team, join_team_by_code, get_user_team,
    get_team_members, get_team_leaderboard,
)

ASK_TEAM_NAME, ASK_TEAM_CODE = range(2)


def _team_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🆕 创建战队", callback_data="team_create"),
         InlineKeyboardButton("🔗 加入战队", callback_data="team_join")],
        [InlineKeyboardButton("📊 战队排行榜", callback_data="team_rank")],
        [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
    ])


def _cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 取消", callback_data="cancel_team")]])


@require_membership
async def show_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示战队信息或战队菜单。"""
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    team = get_user_team(user_id)
    reply = query.message.reply_text if query else update.message.reply_text

    if team:
        members = get_team_members(team["id"])
        lines = [
            f"👥 *战队: {team['name']}*\n",
            f"🔗 邀请码: `{team['invite_code']}`\n",
            f"👤 成员 ({len(members)}/{team.get('max_members', 5)}):\n",
        ]
        for m in members:
            name = m.get("full_name") or m.get("username") or str(m["id"])
            streak = m.get("health_streak", 0) or 0
            gym = m.get("gym_count", 0) or 0
            captain = " 👑" if m["id"] == team["captain_id"] else ""
            lines.append(f"  • {name}{captain} — ❤️{streak}天 🏋️{gym}次")

        total_streak = sum(m.get("health_streak", 0) or 0 for m in members)
        total_gym = sum(m.get("gym_count", 0) or 0 for m in members)
        lines.append(f"\n📊 *战队总计*: ❤️{total_streak}天 🏋️{total_gym}次")
        lines.append("\n💡 分享邀请码给朋友，一起变强！")

        await reply(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 战队排行榜", callback_data="team_rank")],
                [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
            ]),
        )
    else:
        await reply(
            "👥 *战队系统*\n\n"
            "组建2-5人战队，一起打卡、一起竞争！\n\n"
            "战队成员的打卡数据会合并计入战队排行榜。\n"
            "选择你的操作 👇",
            parse_mode="Markdown",
            reply_markup=_team_menu_kb(),
        )


async def start_create_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    existing = get_user_team(user_id)
    if existing:
        await query.message.reply_text(
            f"你已经在战队 *{existing['name']}* 中了。",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    await query.message.reply_text(
        "🆕 *创建战队*\n\n"
        "给你的战队起个名字（2-15字）：",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_TEAM_NAME


async def receive_team_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if len(name) < 2 or len(name) > 15:
        await update.message.reply_text(
            "⚠️ 战队名需要2-15个字，请重新输入：",
            reply_markup=_cancel_kb(),
        )
        return ASK_TEAM_NAME

    user_id = update.effective_user.id
    team = create_team(user_id, name)

    await update.message.reply_text(
        f"✅ *战队创建成功！*\n\n"
        f"👥 战队名: *{team['name']}*\n"
        f"🔗 邀请码: `{team['invite_code']}`\n\n"
        f"把邀请码分享给朋友，让他们发送 /team 加入！",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 查看战队", callback_data="feature_team")],
            [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
        ]),
    )
    return ConversationHandler.END


async def start_join_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    existing = get_user_team(user_id)
    if existing:
        await query.message.reply_text(
            f"你已经在战队 *{existing['name']}* 中了。",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    await query.message.reply_text(
        "🔗 *加入战队*\n\n"
        "请输入战队邀请码（8位字母数字）：",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return ASK_TEAM_CODE


async def receive_team_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    code = update.message.text.strip()
    user_id = update.effective_user.id

    team = join_team_by_code(user_id, code)
    if team:
        await update.message.reply_text(
            f"✅ *成功加入战队！*\n\n"
            f"👥 战队: *{team['name']}*\n\n"
            f"和队友一起打卡，一起上排行榜！💪",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 查看战队", callback_data="feature_team")],
                [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
            ]),
        )
    else:
        await update.message.reply_text(
            "❌ 邀请码无效、战队已满、或你已在其他战队中。\n"
            "请检查后重新输入，或发送 /cancel 取消。",
            reply_markup=_cancel_kb(),
        )
        return ASK_TEAM_CODE

    return ConversationHandler.END


async def show_team_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    teams = get_team_leaderboard(10)
    if not teams:
        await query.message.reply_text(
            "📊 *战队排行榜*\n\n暂无战队数据。\n创建你的战队开始竞争！",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🆕 创建战队", callback_data="team_create")],
                [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
            ]),
        )
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["📊 *战队排行榜*\n"]
    for i, t in enumerate(teams):
        medal = medals[i] if i < 3 else f"  {i+1}."
        lines.append(
            f"{medal} *{t['name']}* ({t['member_count']}人)\n"
            f"    ❤️{t['total_streak']}天 🏋️{t['total_gym']}次"
        )

    lines.append("\n💡 组队打卡，排名更高！")

    await query.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 我的战队", callback_data="feature_team")],
            [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
        ]),
    )


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
            CallbackQueryHandler(start_create_team, pattern="^team_create$"),
            CallbackQueryHandler(start_join_team, pattern="^team_join$"),
        ],
        states={
            ASK_TEAM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_team_name)],
            ASK_TEAM_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_team_code)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_team$"),
        ],
        conversation_timeout=120,
        per_user=True, per_chat=True, allow_reentry=True,
    )

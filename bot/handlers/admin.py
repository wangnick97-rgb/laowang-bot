"""
Admin commands — only usable by users with membership_status='admin'.
"""
from telegram import Update
from telegram.ext import ContextTypes

from db.users import get_user, is_member, upsert_user, set_membership, get_all_active_members
from db.client import get_client


def _is_admin(user_id: int) -> bool:
    user = get_user(user_id)
    return user and user.get("membership_status") == "admin"


async def cmd_addmember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "用法：`/addmember <user_id> [用户名]`\n"
            "例：`/addmember 123456789 小明`\n\n"
            "让对方先给 @userinfobot 发消息获取 user\\_id",
            parse_mode="Markdown",
        )
        return

    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ user_id 必须是数字")
        return

    name = " ".join(context.args[1:]) if len(context.args) > 1 else None
    upsert_user(uid, name, name)
    set_membership(uid, "member")
    await update.message.reply_text(f"✅ 已添加会员：`{uid}` {name or ''}", parse_mode="Markdown")


async def cmd_removemember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("用法：`/removemember <user_id>`", parse_mode="Markdown")
        return

    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ user_id 必须是数字")
        return

    user = get_user(uid)
    if not user:
        await update.message.reply_text(f"❌ 用户 `{uid}` 不存在", parse_mode="Markdown")
        return

    set_membership(uid, "free")
    await update.message.reply_text(f"✅ 已移除会员：`{uid}`", parse_mode="Markdown")


async def cmd_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return

    members = get_all_active_members()

    if not members:
        await update.message.reply_text("当前没有活跃会员。")
        return

    lines = ["👥 *当前会员列表*\n"]
    for m in members:
        name = m.get("username") or str(m["id"])
        lines.append(f"• `{m['id']}` @{name}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return

    db = get_client()

    # 总用户数
    all_users = db.table("users").select("id", count="exact").execute()
    total_users = all_users.count or 0

    # 活跃会员数
    members = get_all_active_members()
    member_count = len(members)

    # 今日使用次数 & token
    from datetime import date
    today = date.today().isoformat()
    today_logs = (
        db.table("usage_logs")
        .select("feature, input_tokens, output_tokens")
        .gte("created_at", f"{today}T00:00:00")
        .execute()
    )
    logs = today_logs.data or []
    today_calls = len(logs)
    today_input = sum(l.get("input_tokens", 0) for l in logs)
    today_output = sum(l.get("output_tokens", 0) for l in logs)

    # 功能使用分布
    feature_counts = {}
    for l in logs:
        f = l.get("feature", "unknown")
        feature_counts[f] = feature_counts.get(f, 0) + 1
    feature_lines = "\n".join(
        f"  • {k}: {v} 次" for k, v in sorted(feature_counts.items(), key=lambda x: -x[1])
    ) or "  暂无"

    text = (
        f"📊 *数据面板*\n\n"
        f"👥 总用户：{total_users}\n"
        f"💎 活跃会员：{member_count}\n\n"
        f"*今日使用*\n"
        f"  调用次数：{today_calls}\n"
        f"  Input tokens：{today_input:,}\n"
        f"  Output tokens：{today_output:,}\n\n"
        f"*功能分布（今日）*\n{feature_lines}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

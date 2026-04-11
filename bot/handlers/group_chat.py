"""
群聊活跃追踪系统
- 监测用户每日在群内的发言次数
- 达到 20 次：奖励积分
- 达到 60 次：奖励更多积分
- Admin 可查看群聊活跃统计 /groupstats
"""
import logging
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from db.client import get_client
from db.users import get_user, upsert_user, get_admin_ids

logger = logging.getLogger(__name__)

# 里程碑配置: {次数: 积分奖励}
CHAT_MILESTONES = {
    20: 30,   # 20条消息 → 30积分
    60: 80,   # 60条消息 → 80积分
}


def _get_or_create_daily(user_id: int, today: str) -> dict:
    """获取或创建用户今日群聊记录。"""
    db = get_client()
    result = (
        db.table("group_chat_daily")
        .select("*")
        .eq("user_id", user_id)
        .eq("chat_date", today)
        .maybe_single()
        .execute()
    )
    if result and result.data:
        return result.data

    # 创建新记录
    db.table("group_chat_daily").insert({
        "user_id": user_id,
        "chat_date": today,
        "message_count": 0,
        "reward_20": False,
        "reward_60": False,
    }).execute()
    return {
        "user_id": user_id,
        "chat_date": today,
        "message_count": 0,
        "reward_20": False,
        "reward_60": False,
    }


async def track_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """每条群聊消息触发：计数+检查里程碑。"""
    if not update.effective_user or not update.message:
        return
    # 忽略 bot 自己的消息
    if update.effective_user.is_bot:
        return

    user_id = update.effective_user.id
    today = date.today().isoformat()

    # 确保用户已注册
    tg_user = update.effective_user
    upsert_user(tg_user.id, tg_user.username, tg_user.full_name)

    db = get_client()
    record = _get_or_create_daily(user_id, today)
    new_count = (record.get("message_count", 0) or 0) + 1

    update_data = {"message_count": new_count}

    # 检查里程碑
    points_earned = 0
    milestone_hit = None

    if new_count >= 60 and not record.get("reward_60"):
        points_earned = CHAT_MILESTONES[60]
        update_data["reward_60"] = True
        milestone_hit = 60
    elif new_count >= 20 and not record.get("reward_20"):
        points_earned = CHAT_MILESTONES[20]
        update_data["reward_20"] = True
        milestone_hit = 20

    # 更新计数
    db.table("group_chat_daily").update(update_data).eq(
        "user_id", user_id
    ).eq("chat_date", today).execute()

    # 发积分 + 通知
    if points_earned > 0:
        user_row = db.table("users").select("points").eq("id", user_id).maybe_single().execute()
        current_points = (user_row.data or {}).get("points", 0) or 0
        db.table("users").update({"points": current_points + points_earned}).eq("id", user_id).execute()

        name = tg_user.full_name or tg_user.username or str(user_id)
        await update.message.reply_text(
            f"🎉 *群聊活跃奖励！*\n\n"
            f"恭喜 *{name}* 今日群内发言达到 *{milestone_hit}* 条！\n"
            f"获得 *+{points_earned}* 积分 🪙\n\n"
            + ("💡 继续聊到60条还有更多奖励哦！" if milestone_hit == 20 else "🔥 你是今日群聊之星！"),
            parse_mode="Markdown",
        )


async def cmd_groupstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin命令：查看今日群聊活跃统计。"""
    user = get_user(update.effective_user.id)
    if not user or user.get("membership_status") != "admin":
        return

    today = date.today().isoformat()
    db = get_client()

    # 今日所有群聊记录
    rows = (
        db.table("group_chat_daily")
        .select("user_id, message_count, reward_20, reward_60")
        .eq("chat_date", today)
        .order("message_count", desc=True)
        .limit(20)
        .execute()
    )
    records = rows.data or []

    if not records:
        await update.message.reply_text("📊 今日暂无群聊数据。")
        return

    total_messages = sum(r.get("message_count", 0) for r in records)
    active_users = len(records)

    lines = [f"📊 *今日群聊统计* ({today})\n"]
    lines.append(f"👥 活跃人数: *{active_users}*")
    lines.append(f"💬 总消息数: *{total_messages}*\n")
    lines.append("*TOP 发言排行:*")

    for i, r in enumerate(records[:10], 1):
        uid = r["user_id"]
        u = get_user(uid)
        name = (u.get("full_name") or u.get("username") or str(uid)) if u else str(uid)
        count = r["message_count"]
        badges = ""
        if r.get("reward_60"):
            badges = " 🔥🔥"
        elif r.get("reward_20"):
            badges = " 🔥"
        lines.append(f"  {i}. {name}: *{count}* 条{badges}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_mychat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """用户命令：查看自己今日群聊数据。"""
    user_id = update.effective_user.id
    today = date.today().isoformat()
    db = get_client()

    record = (
        db.table("group_chat_daily")
        .select("message_count, reward_20, reward_60")
        .eq("user_id", user_id)
        .eq("chat_date", today)
        .maybe_single()
        .execute()
    )
    data = record.data if record else None

    if not data:
        count = 0
    else:
        count = data.get("message_count", 0)

    # 下一个里程碑
    if count < 20:
        next_milestone = 20
        next_reward = CHAT_MILESTONES[20]
        remaining = 20 - count
    elif count < 60:
        next_milestone = 60
        next_reward = CHAT_MILESTONES[60]
        remaining = 60 - count
    else:
        next_milestone = None
        next_reward = 0
        remaining = 0

    progress_20 = "✅" if (data and data.get("reward_20")) else f"{'🔥' if count >= 20 else '⬜'}"
    progress_60 = "✅" if (data and data.get("reward_60")) else f"{'🔥' if count >= 60 else '⬜'}"

    text = (
        f"💬 *今日群聊数据*\n\n"
        f"📊 今日发言: *{count}* 条\n\n"
        f"*里程碑:*\n"
        f"  {progress_20} 20条 → +{CHAT_MILESTONES[20]}积分\n"
        f"  {progress_60} 60条 → +{CHAT_MILESTONES[60]}积分\n"
    )
    if next_milestone:
        text += f"\n💡 再发 *{remaining}* 条即可获得 *+{next_reward}* 积分！"
    else:
        text += f"\n🏆 今日所有里程碑已达成！"

    await update.message.reply_text(text, parse_mode="Markdown")

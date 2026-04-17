"""
积分系统数据层
- 签到得积分（连续签到加成）
- 每日宝箱（随机奖励）
- 签到保护卡
- 成就系统
"""
from __future__ import annotations
import random
from datetime import date, timedelta
from db.client import get_client


def get_points_info(user_id: int) -> dict:
    db = get_client()
    result = (
        db.table("users")
        .select("points, checkin_streak, last_checkin_date, streak_shields, badges")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    if result and result.data:
        return result.data
    return {"points": 0, "checkin_streak": 0, "last_checkin_date": None, "streak_shields": 0, "badges": []}


# ── 每日宝箱配置 ──────────────────────────────────────────────────────────────
# (概率权重, 奖励名, 积分, emoji)
_CHEST_TABLE = [
    (40, "铜币袋",     5,  "🪙"),
    (25, "银币袋",     15, "🥈"),
    (15, "金币袋",     30, "🥇"),
    (10, "宝石袋",     50, "💎"),
    (5,  "保护卡 ×1",  0,  "🛡️"),   # 特殊：送保护卡
    (3,  "钻石宝箱",   100, "👑"),
    (2,  "传说宝箱",   200, "🐉"),
]


def open_chest(user_id: int) -> dict:
    """开宝箱，返回 {"name", "points", "emoji", "is_shield"}"""
    weights = [item[0] for item in _CHEST_TABLE]
    chosen = random.choices(_CHEST_TABLE, weights=weights, k=1)[0]
    _, name, points, emoji = chosen
    is_shield = name == "保护卡 ×1"

    db = get_client()
    info = get_points_info(user_id)

    updates = {}
    if is_shield:
        updates["streak_shields"] = (info.get("streak_shields", 0) or 0) + 1
    if points > 0:
        updates["points"] = (info.get("points", 0) or 0) + points

    if updates:
        db.table("users").update(updates).eq("id", user_id).execute()

    return {"name": name, "points": points, "emoji": emoji, "is_shield": is_shield}


# ── 签到（含保护卡逻辑）─────────────────────────────────────────────────────

def do_checkin(user_id: int) -> dict:
    db = get_client()
    info = get_points_info(user_id)
    today = date.today().isoformat()

    if info.get("last_checkin_date") == today:
        return {
            "success": False,
            "points_earned": 0,
            "streak": info.get("checkin_streak", 0),
            "total_points": info.get("points", 0),
            "shield_used": False,
        }

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    old_streak = info.get("checkin_streak", 0) or 0
    shields = info.get("streak_shields", 0) or 0
    shield_used = False

    if info.get("last_checkin_date") == yesterday:
        new_streak = old_streak + 1
    elif old_streak > 0 and shields > 0:
        # 断签但有保护卡 → 自动使用
        new_streak = old_streak + 1
        shields -= 1
        shield_used = True
    else:
        new_streak = 1

    base_points = 10
    streak_bonus = min(new_streak - 1, 20) * 2

    # 🎲 签到盲盒：每次签到额外的"今日手气"加成（变量奖励，增强成瘾性）
    # 权重：55% 平平无奇 / 25% 小惊喜 / 12% 中奖 / 6% 大奖 / 2% 头奖
    lucky_table = [
        (55, 0,  "平"),
        (25, 3,  "🍀 小惊喜"),
        (12, 7,  "✨ 中奖"),
        (6,  15, "💫 大奖"),
        (2,  30, "🎰 头奖！"),
    ]
    weights = [row[0] for row in lucky_table]
    _, lucky_bonus, lucky_label = random.choices(lucky_table, weights=weights, k=1)[0]

    points_earned = base_points + streak_bonus + lucky_bonus

    new_total = (info.get("points", 0) or 0) + points_earned

    update_data = {
        "points": new_total,
        "checkin_streak": new_streak,
        "last_checkin_date": today,
    }
    if shield_used:
        update_data["streak_shields"] = shields

    db.table("users").update(update_data).eq("id", user_id).execute()

    # 检查并解锁成就
    new_badges = check_and_unlock_badges(user_id, new_streak, new_total)

    return {
        "success": True,
        "points_earned": points_earned,
        "base_points": base_points,
        "streak_bonus": streak_bonus,
        "lucky_bonus": lucky_bonus,
        "lucky_label": lucky_label,
        "streak": new_streak,
        "total_points": new_total,
        "shield_used": shield_used,
        "new_badges": new_badges,
    }


# ── 成就系统 ──────────────────────────────────────────────────────────────────

ACHIEVEMENTS = {
    "first_checkin":   {"name": "初来乍到",     "emoji": "🌱", "desc": "完成第一次签到"},
    "streak_3":        {"name": "小试牛刀",     "emoji": "🔥", "desc": "连续签到 3 天"},
    "streak_7":        {"name": "周周不落",     "emoji": "⭐", "desc": "连续签到 7 天"},
    "streak_14":       {"name": "半月达人",     "emoji": "💫", "desc": "连续签到 14 天"},
    "streak_30":       {"name": "月度之星",     "emoji": "💎", "desc": "连续签到 30 天"},
    "streak_60":       {"name": "钢铁意志",     "emoji": "👑", "desc": "连续签到 60 天"},
    "streak_100":      {"name": "传说级自律",   "emoji": "🐉", "desc": "连续签到 100 天"},
    "points_100":      {"name": "小有积蓄",     "emoji": "💰", "desc": "累计 100 积分"},
    "points_500":      {"name": "积分大户",     "emoji": "🏦", "desc": "累计 500 积分"},
    "points_1000":     {"name": "积分富翁",     "emoji": "💸", "desc": "累计 1000 积分"},
    "chest_dragon":    {"name": "欧皇降临",     "emoji": "🎰", "desc": "开出传说宝箱"},
}


def check_and_unlock_badges(user_id: int, streak: int, total_points: int) -> list[str]:
    """检查并解锁新成就，返回新解锁的 badge IDs。"""
    info = get_points_info(user_id)
    current_badges = info.get("badges") or []
    new_badges = []

    checks = {
        "first_checkin": True,
        "streak_3": streak >= 3,
        "streak_7": streak >= 7,
        "streak_14": streak >= 14,
        "streak_30": streak >= 30,
        "streak_60": streak >= 60,
        "streak_100": streak >= 100,
        "points_100": total_points >= 100,
        "points_500": total_points >= 500,
        "points_1000": total_points >= 1000,
    }

    for badge_id, condition in checks.items():
        if condition and badge_id not in current_badges:
            new_badges.append(badge_id)

    if new_badges:
        db = get_client()
        updated = current_badges + new_badges
        db.table("users").update({"badges": updated}).eq("id", user_id).execute()

    return new_badges


def unlock_special_badge(user_id: int, badge_id: str):
    """手动解锁特殊成就（如开出传说宝箱）"""
    info = get_points_info(user_id)
    current = info.get("badges") or []
    if badge_id not in current:
        db = get_client()
        db.table("users").update({"badges": current + [badge_id]}).eq("id", user_id).execute()


def get_leaderboard(limit: int = 10) -> list[dict]:
    db = get_client()
    result = (
        db.table("users")
        .select("id, username, full_name, points, checkin_streak")
        .eq("is_active", True)
        .gt("points", 0)
        .order("points", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def redeem_points(user_id: int, cost: int, reward_name: str) -> bool:
    info = get_points_info(user_id)
    current = info.get("points", 0) or 0
    if current < cost:
        return False
    db = get_client()
    db.table("users").update({"points": current - cost}).eq("id", user_id).execute()
    return True

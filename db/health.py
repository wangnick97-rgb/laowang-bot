"""
健康执行系统数据层
- 健康档案 (health_profiles)
- 健身打卡 (gym_logs)
- 健康打卡 (health_checkins)
- 积分整合（复用 users.points）
"""
from __future__ import annotations
from datetime import date, timedelta
from db.client import get_client


# ── 健康档案 ─────────────────────────────────────────────────────────────────

def get_health_profile(user_id: int) -> dict | None:
    db = get_client()
    result = (
        db.table("health_profiles")
        .select("*")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    return result.data if result else None


def upsert_health_profile(user_id: int, data: dict) -> dict:
    db = get_client()
    row = {"user_id": user_id, **data, "updated_at": "now()"}
    result = db.table("health_profiles").upsert(row).execute()
    return result.data[0] if result.data else row


# ── 健身打卡 ─────────────────────────────────────────────────────────────────

def do_gym_log(user_id: int, workout_type: str, duration_min: int, intensity: int, notes: str = "") -> dict:
    """记录健身打卡，返回积分信息。每天仅可打卡一次。"""
    db = get_client()
    today = date.today().isoformat()

    # 检查今日是否已打卡
    existing = (
        db.table("gym_logs")
        .select("id")
        .eq("user_id", user_id)
        .eq("log_date", today)
        .maybe_single()
        .execute()
    )
    if existing and existing.data:
        return {"success": False, "reason": "already_logged"}

    # 计算积分
    base_points = 8
    # 强度加分: intensity 4 → +2, intensity 5 → +5
    intensity_bonus = {1: 0, 2: 0, 3: 0, 4: 2, 5: 5}.get(intensity, 0)
    points_earned = base_points + intensity_bonus

    # 插入记录
    db.table("gym_logs").insert({
        "user_id": user_id,
        "log_date": today,
        "workout_type": workout_type,
        "duration_min": duration_min,
        "intensity": intensity,
        "notes": notes,
        "points_earned": points_earned,
    }).execute()

    # 更新 users 表的 gym_count 和积分
    user = db.table("users").select("points, gym_count").eq("id", user_id).maybe_single().execute()
    user_data = user.data or {"points": 0, "gym_count": 0}
    new_gym_count = (user_data.get("gym_count") or 0) + 1
    new_points = (user_data.get("points") or 0) + points_earned

    db.table("users").update({
        "points": new_points,
        "gym_count": new_gym_count,
        "last_gym_date": today,
    }).eq("id", user_id).execute()

    return {
        "success": True,
        "points_earned": points_earned,
        "total_points": new_points,
        "gym_count": new_gym_count,
        "workout_type": workout_type,
        "duration_min": duration_min,
        "intensity": intensity,
    }


# ── 健康打卡 ─────────────────────────────────────────────────────────────────

def do_health_checkin(user_id: int, mood: str, note: str = "") -> dict:
    """健康打卡。独立连续天数追踪，积分与通用签到共用池。"""
    db = get_client()
    today = date.today().isoformat()

    # 检查今日是否已打卡
    existing = (
        db.table("health_checkins")
        .select("id")
        .eq("user_id", user_id)
        .eq("checkin_date", today)
        .maybe_single()
        .execute()
    )
    if existing and existing.data:
        return {"success": False, "reason": "already_checked"}

    # 获取用户健康连续天数
    user = (
        db.table("users")
        .select("points, health_streak, last_health_checkin")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    user_data = user.data or {"points": 0, "health_streak": 0, "last_health_checkin": None}

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    old_streak = user_data.get("health_streak") or 0

    if user_data.get("last_health_checkin") == yesterday:
        new_streak = old_streak + 1
    else:
        new_streak = 1

    # 积分计算
    base_points = 5
    streak_bonus = 0
    if new_streak >= 30:
        streak_bonus = 50
    elif new_streak >= 14:
        streak_bonus = 20
    elif new_streak >= 7:
        streak_bonus = 10
    elif new_streak >= 3:
        streak_bonus = 5
    points_earned = base_points + streak_bonus

    new_total = (user_data.get("points") or 0) + points_earned

    # 插入打卡记录
    db.table("health_checkins").insert({
        "user_id": user_id,
        "checkin_date": today,
        "mood": mood,
        "note": note,
        "health_streak": new_streak,
        "points_earned": points_earned,
    }).execute()

    # 更新 users 表
    db.table("users").update({
        "points": new_total,
        "health_streak": new_streak,
        "last_health_checkin": today,
    }).eq("id", user_id).execute()

    return {
        "success": True,
        "points_earned": points_earned,
        "streak": new_streak,
        "total_points": new_total,
        "mood": mood,
        "streak_bonus": streak_bonus,
    }


# ── 排行榜 ───────────────────────────────────────────────────────────────────

def get_health_leaderboard(limit: int = 10) -> list[dict]:
    """健康连续打卡排行榜。"""
    db = get_client()
    result = (
        db.table("users")
        .select("id, username, full_name, health_streak, gym_count, points")
        .eq("is_active", True)
        .gt("health_streak", 0)
        .order("health_streak", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_gym_leaderboard(limit: int = 10) -> list[dict]:
    """健身打卡次数排行榜。"""
    db = get_client()
    result = (
        db.table("users")
        .select("id, username, full_name, gym_count, health_streak, points")
        .eq("is_active", True)
        .gt("gym_count", 0)
        .order("gym_count", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


# ── 挑战任务 ─────────────────────────────────────────────────────────────────

def get_active_challenges() -> list[dict]:
    """获取当前活跃的挑战。"""
    db = get_client()
    today = date.today().isoformat()
    result = (
        db.table("challenges")
        .select("*")
        .eq("is_active", True)
        .lte("start_date", today)
        .gte("end_date", today)
        .order("challenge_type")
        .execute()
    )
    return result.data or []


def get_user_challenge_progress(user_id: int, challenge_id: int) -> dict | None:
    db = get_client()
    result = (
        db.table("user_challenges")
        .select("*")
        .eq("user_id", user_id)
        .eq("challenge_id", challenge_id)
        .maybe_single()
        .execute()
    )
    return result.data if result else None


def join_challenge(user_id: int, challenge_id: int) -> bool:
    """加入挑战。返回 True 如果成功。"""
    db = get_client()
    existing = get_user_challenge_progress(user_id, challenge_id)
    if existing:
        return False
    db.table("user_challenges").insert({
        "user_id": user_id,
        "challenge_id": challenge_id,
        "current_progress": 0,
        "completed": False,
    }).execute()
    return True


def update_challenge_progress(user_id: int, target_type: str, increment: int = 1):
    """根据行为类型自动更新该用户所有相关挑战的进度。"""
    db = get_client()
    today = date.today().isoformat()

    # 找到该用户参与的、匹配此target_type的活跃挑战
    active = get_active_challenges()
    matching = [c for c in active if c["target_type"] == target_type]

    for challenge in matching:
        cid = challenge["id"]
        progress = get_user_challenge_progress(user_id, cid)
        if not progress or progress.get("completed"):
            continue

        new_val = (progress.get("current_progress") or 0) + increment
        target = challenge["target_value"]
        completed = new_val >= target

        update_data = {"current_progress": new_val}
        if completed:
            from datetime import datetime, timezone
            update_data["completed"] = True
            update_data["completed_at"] = datetime.now(timezone.utc).isoformat()

            # 发放奖励积分
            reward = challenge.get("reward_points", 0)
            if reward > 0:
                user = db.table("users").select("points").eq("id", user_id).maybe_single().execute()
                new_points = ((user.data or {}).get("points", 0) or 0) + reward
                db.table("users").update({"points": new_points}).eq("id", user_id).execute()

        db.table("user_challenges").update(update_data).eq("user_id", user_id).eq("challenge_id", cid).execute()


def get_user_all_challenges(user_id: int) -> list[dict]:
    """获取用户参与的所有活跃挑战及其进度。"""
    active = get_active_challenges()
    result = []
    for c in active:
        progress = get_user_challenge_progress(user_id, c["id"])
        result.append({
            **c,
            "joined": progress is not None,
            "current_progress": (progress or {}).get("current_progress", 0),
            "completed": (progress or {}).get("completed", False),
        })
    return result


# ── 战队 ─────────────────────────────────────────────────────────────────────

def create_team(captain_id: int, name: str) -> dict:
    """创建战队，返回战队信息。"""
    import hashlib
    code = hashlib.md5(f"{captain_id}{name}{date.today()}".encode()).hexdigest()[:8].upper()
    db = get_client()
    result = db.table("teams").insert({
        "name": name,
        "captain_id": captain_id,
        "invite_code": code,
    }).execute()
    team = result.data[0]
    # 队长自动加入
    db.table("team_members").insert({
        "team_id": team["id"],
        "user_id": captain_id,
    }).execute()
    return team


def join_team_by_code(user_id: int, code: str) -> dict | None:
    """通过邀请码加入战队。返回战队信息或None。"""
    db = get_client()
    team_result = db.table("teams").select("*").eq("invite_code", code.upper()).maybe_single().execute()
    if not team_result or not team_result.data:
        return None
    team = team_result.data

    # 检查是否已加入
    existing = (
        db.table("team_members")
        .select("user_id")
        .eq("team_id", team["id"])
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if existing and existing.data:
        return None  # 已加入

    # 检查人数上限
    members = db.table("team_members").select("user_id").eq("team_id", team["id"]).execute()
    if len(members.data or []) >= team.get("max_members", 5):
        return None  # 满员

    db.table("team_members").insert({
        "team_id": team["id"],
        "user_id": user_id,
    }).execute()
    return team


def get_user_team(user_id: int) -> dict | None:
    """获取用户所在的战队。"""
    db = get_client()
    membership = (
        db.table("team_members")
        .select("team_id")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not membership or not membership.data:
        return None
    team_id = membership.data["team_id"]
    team_result = db.table("teams").select("*").eq("id", team_id).maybe_single().execute()
    return team_result.data if team_result else None


def get_team_members(team_id: int) -> list[dict]:
    """获取战队成员列表（含用户信息）。"""
    db = get_client()
    members = db.table("team_members").select("user_id").eq("team_id", team_id).execute()
    if not members.data:
        return []
    user_ids = [m["user_id"] for m in members.data]
    users = db.table("users").select(
        "id, username, full_name, health_streak, gym_count, points"
    ).in_("id", user_ids).execute()
    return users.data or []


def get_team_leaderboard(limit: int = 10) -> list[dict]:
    """战队排行榜：按成员健康打卡总天数排名。"""
    db = get_client()
    teams = db.table("teams").select("id, name, captain_id").execute()
    results = []
    for team in (teams.data or []):
        members = get_team_members(team["id"])
        total_streak = sum(m.get("health_streak", 0) or 0 for m in members)
        total_gym = sum(m.get("gym_count", 0) or 0 for m in members)
        results.append({
            **team,
            "member_count": len(members),
            "total_streak": total_streak,
            "total_gym": total_gym,
            "score": total_streak + total_gym,
        })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


# ── 用户统计（成绩单用）─────────────────────────────────────────────────────

def get_user_health_stats(user_id: int) -> dict:
    """获取用户健康板块综合统计。"""
    db = get_client()
    today = date.today()

    user = (
        db.table("users")
        .select("points, health_streak, gym_count, full_name, username")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    user_data = user.data or {}

    # 本周训练次数
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    week_gym = (
        db.table("gym_logs")
        .select("id")
        .eq("user_id", user_id)
        .gte("log_date", week_start)
        .execute()
    )

    # 本周卡路里打卡天数
    week_cal = (
        db.table("calorie_logs")
        .select("log_date")
        .eq("user_id", user_id)
        .gte("log_date", week_start)
        .execute()
    )
    cal_days = len(set(r.get("log_date") for r in (week_cal.data or [])))

    # 本周健康打卡天数
    week_health = (
        db.table("health_checkins")
        .select("id")
        .eq("user_id", user_id)
        .gte("checkin_date", week_start)
        .execute()
    )

    # 排名
    rank_result = (
        db.table("users")
        .select("id")
        .eq("is_active", True)
        .gt("health_streak", 0)
        .order("health_streak", desc=True)
        .execute()
    )
    rank = 0
    for i, r in enumerate(rank_result.data or []):
        if r["id"] == user_id:
            rank = i + 1
            break

    return {
        "name": user_data.get("full_name") or user_data.get("username") or str(user_id),
        "points": user_data.get("points", 0) or 0,
        "health_streak": user_data.get("health_streak", 0) or 0,
        "gym_count": user_data.get("gym_count", 0) or 0,
        "week_gym": len(week_gym.data or []),
        "week_cal_days": cal_days,
        "week_health": len(week_health.data or []),
        "rank": rank,
    }

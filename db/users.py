from __future__ import annotations
from datetime import date
from typing import Optional
from db.client import get_client
from config.settings import DAILY_USAGE_LIMIT


def get_user(user_id: int) -> Optional[dict]:
    db = get_client()
    result = db.table("users").select("*").eq("id", user_id).maybe_single().execute()
    return result.data


def upsert_user(user_id: int, username: Optional[str], full_name: Optional[str]) -> dict:
    db = get_client()
    result = (
        db.table("users")
        .upsert(
            {"id": user_id, "username": username, "full_name": full_name},
            on_conflict="id",
            ignore_duplicates=True,
        )
        .execute()
    )
    return get_user(user_id)


def is_member(user: dict) -> bool:
    """Returns True if user has active membership or is admin."""
    if not user or not user.get("is_active"):
        return False
    status = user.get("membership_status", "free")
    if status == "admin":
        return True
    if status != "member":
        return False
    expires = user.get("membership_expires_at")
    if expires is None:
        return True  # No expiry set = permanent member
    from datetime import datetime, timezone
    expiry_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    return expiry_dt > datetime.now(timezone.utc)


def check_and_increment_usage(user_id: int) -> bool:
    """
    Returns True if user is within daily limit, and increments their count.
    Returns False if limit exceeded.
    """
    db = get_client()
    user = get_user(user_id)
    if not user:
        return False

    today = date.today().isoformat()
    # Reset counter if it's a new day
    if user.get("usage_reset_date") != today:
        db.table("users").update(
            {"daily_usage_count": 0, "usage_reset_date": today}
        ).eq("id", user_id).execute()
        user["daily_usage_count"] = 0

    if user["daily_usage_count"] >= DAILY_USAGE_LIMIT:
        return False

    db.table("users").update(
        {"daily_usage_count": user["daily_usage_count"] + 1}
    ).eq("id", user_id).execute()
    return True


def get_all_active_members() -> list[dict]:
    """Returns all users with active membership for broadcast."""
    db = get_client()
    result = (
        db.table("users")
        .select("id, username")
        .in_("membership_status", ["member", "admin"])
        .eq("is_active", True)
        .execute()
    )
    return result.data or []


def set_membership(user_id: int, status: str, expires_at: Optional[str] = None):
    db = get_client()
    db.table("users").update(
        {"membership_status": status, "membership_expires_at": expires_at}
    ).eq("id", user_id).execute()

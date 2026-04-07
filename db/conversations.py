from __future__ import annotations
from typing import Optional, Tuple
from db.client import get_client


def save_state(user_id: int, feature: str, state: int, data: dict):
    db = get_client()
    db.table("conversation_states").upsert({
        "user_id": user_id,
        "feature": feature,
        "current_state": state,
        "collected_data": data,
    }).execute()


def get_state(user_id: int, feature: str) -> Optional[Tuple[int, dict]]:
    db = get_client()
    result = (
        db.table("conversation_states")
        .select("current_state, collected_data")
        .eq("user_id", user_id)
        .eq("feature", feature)
        .maybe_single()
        .execute()
    )
    if result.data:
        return result.data["current_state"], result.data["collected_data"]
    return None


def clear_state(user_id: int, feature: str):
    db = get_client()
    db.table("conversation_states").delete().eq("user_id", user_id).eq("feature", feature).execute()

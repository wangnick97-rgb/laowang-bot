from db.client import get_client


def log_usage(user_id: int, feature: str, model: str, input_tokens: int, output_tokens: int):
    db = get_client()
    db.table("usage_logs").insert({
        "user_id": user_id,
        "feature": feature,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }).execute()


def get_daily_usage_count(user_id: int) -> int:
    from datetime import date
    db = get_client()
    today = date.today().isoformat()
    result = (
        db.table("usage_logs")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gte("created_at", f"{today}T00:00:00")
        .execute()
    )
    return result.count or 0

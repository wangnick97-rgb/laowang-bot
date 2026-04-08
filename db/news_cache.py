from __future__ import annotations
from datetime import date
from typing import Optional
from db.client import get_client


def get_cached_summary(category: str, cache_date: Optional[date] = None) -> Optional[str]:
    if cache_date is None:
        cache_date = date.today()
    db = get_client()
    try:
        result = (
            db.table("news_cache")
            .select("claude_summary")
            .eq("cache_date", cache_date.isoformat())
            .eq("category", category)
            .maybe_single()
            .execute()
        )
        if result and result.data:
            return result.data["claude_summary"]
    except Exception:
        pass
    return None


def save_cache(category: str, raw_articles: list, claude_summary: str, cache_date: Optional[date] = None):
    if cache_date is None:
        cache_date = date.today()
    db = get_client()
    db.table("news_cache").upsert({
        "cache_date": cache_date.isoformat(),
        "category": category,
        "raw_articles": raw_articles,
        "claude_summary": claude_summary,
    }).execute()

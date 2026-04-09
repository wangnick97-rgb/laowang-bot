"""
FastAPI app: serves Telegram webhook + Mini App API + static files.
Replaces ptb's built-in run_webhook().
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta
from collections import defaultdict

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from telegram import Update

from config.settings import TELEGRAM_BOT_TOKEN, BOT_MODE, WEBHOOK_URL, PORT
from webapp.auth import get_current_user
from db.client import get_client
from db.points import get_points_info, get_leaderboard, ACHIEVEMENTS
from db.health import get_user_health_stats

logger = logging.getLogger(__name__)

# ── ptb Application (initialized at startup) ────────────────────────────────
_ptb_app = None


def _build_ptb_app():
    from main import build_app
    return build_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop ptb Application with FastAPI lifecycle."""
    global _ptb_app
    _ptb_app = _build_ptb_app()
    await _ptb_app.initialize()
    await _ptb_app.start()

    # Set webhook
    if BOT_MODE == "webhook" and WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}"
        await _ptb_app.bot.set_webhook(url=webhook_url, allowed_updates=["message", "callback_query"])
        logger.info("Webhook set: %s", webhook_url)

    # Start updater processing (without running its own web server)
    asyncio.create_task(_ptb_app.updater.start_webhook(
        listen="127.0.0.1",
        port=0,  # Don't actually listen; we feed updates manually
        url_path=TELEGRAM_BOT_TOKEN,
        webhook_url="",  # Already set above
        drop_pending_updates=False,
    )) if False else None  # Skip updater; we push to update_queue directly

    logger.info("ptb Application started")
    yield

    await _ptb_app.stop()
    await _ptb_app.shutdown()
    logger.info("ptb Application stopped")


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

# ── Static files (Mini App frontend) ────────────────────────────────────────
import os
_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/webapp", StaticFiles(directory=_static_dir, html=True), name="webapp")


# ── Telegram Webhook endpoint ────────────────────────────────────────────────

@app.post(f"/{TELEGRAM_BOT_TOKEN}")
async def telegram_webhook(request: Request):
    """Receive Telegram updates and feed to ptb."""
    data = await request.json()
    update = Update.de_json(data, _ptb_app.bot)
    await _ptb_app.process_update(update)
    return JSONResponse(content={"ok": True})


# ── Mini App API endpoints ───────────────────────────────────────────────────

@app.get("/api/me")
async def api_me(user: dict = Depends(get_current_user)):
    """User dashboard: points, streaks, rank, membership."""
    user_id = user["id"]
    db = get_client()

    row = db.table("users").select(
        "points, checkin_streak, health_streak, gym_count, badges, "
        "membership_status, membership_expires_at, full_name, username"
    ).eq("id", user_id).maybe_single().execute()

    if not row or not row.data:
        raise HTTPException(status_code=404, detail="User not found")

    u = row.data

    # Compute rank
    all_users = db.table("users").select("id").eq("is_active", True).gt("points", 0).order("points", desc=True).execute()
    rank = 0
    for i, r in enumerate(all_users.data or []):
        if r["id"] == user_id:
            rank = i + 1
            break

    return {
        "name": u.get("full_name") or u.get("username") or str(user_id),
        "points": u.get("points", 0) or 0,
        "checkin_streak": u.get("checkin_streak", 0) or 0,
        "health_streak": u.get("health_streak", 0) or 0,
        "gym_count": u.get("gym_count", 0) or 0,
        "badges": u.get("badges") or [],
        "membership_status": u.get("membership_status", "free"),
        "membership_expires_at": u.get("membership_expires_at"),
        "rank": rank,
    }


@app.get("/api/checkins")
async def api_checkins(months: int = 3, user: dict = Depends(get_current_user)):
    """Check-in dates for calendar heatmap."""
    user_id = user["id"]
    db = get_client()
    start = (date.today() - timedelta(days=months * 30)).isoformat()

    general = db.table("checkin_logs").select("checkin_date").eq("user_id", user_id).gte("checkin_date", start).execute()
    health = db.table("health_checkins").select("checkin_date").eq("user_id", user_id).gte("checkin_date", start).execute()
    gym = db.table("gym_logs").select("log_date").eq("user_id", user_id).gte("log_date", start).execute()

    return {
        "general": sorted(set(r["checkin_date"] for r in (general.data or []))),
        "health": sorted(set(r["checkin_date"] for r in (health.data or []))),
        "gym": sorted(set(r["log_date"] for r in (gym.data or []))),
    }


@app.get("/api/calories")
async def api_calories(days: int = 30, user: dict = Depends(get_current_user)):
    """Daily calorie totals for chart."""
    user_id = user["id"]
    db = get_client()
    start = (date.today() - timedelta(days=days)).isoformat()

    rows = db.table("calorie_logs").select(
        "log_date, estimated_calories, estimated_protein, estimated_carbs, estimated_fat"
    ).eq("user_id", user_id).gte("log_date", start).order("log_date").execute()

    # Aggregate by date
    by_date = defaultdict(lambda: {"calories": 0, "protein": 0, "carbs": 0, "fat": 0})
    for r in (rows.data or []):
        d = r["log_date"]
        by_date[d]["calories"] += r.get("estimated_calories") or 0
        by_date[d]["protein"] += float(r.get("estimated_protein") or 0)
        by_date[d]["carbs"] += float(r.get("estimated_carbs") or 0)
        by_date[d]["fat"] += float(r.get("estimated_fat") or 0)

    return [
        {"date": d, **vals}
        for d, vals in sorted(by_date.items())
    ]


@app.get("/api/workouts")
async def api_workouts(user: dict = Depends(get_current_user)):
    """Workout statistics."""
    user_id = user["id"]
    db = get_client()

    rows = db.table("gym_logs").select(
        "log_date, workout_type, intensity"
    ).eq("user_id", user_id).order("log_date", desc=True).limit(200).execute()

    data = rows.data or []
    by_type = defaultdict(int)
    by_intensity = defaultdict(int)
    week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    this_week = 0

    for r in data:
        by_type[r.get("workout_type", "other")] += 1
        by_intensity[str(r.get("intensity", 3))] += 1
        if r.get("log_date", "") >= week_start:
            this_week += 1

    return {
        "total": len(data),
        "this_week": this_week,
        "by_type": dict(by_type),
        "by_intensity": dict(by_intensity),
    }


@app.get("/api/leaderboard")
async def api_leaderboard():
    """Top 10 users by points. No auth required."""
    top = get_leaderboard(10)
    return [
        {
            "rank": i + 1,
            "name": u.get("full_name") or u.get("username") or str(u["id"]),
            "points": u.get("points", 0),
            "checkin_streak": u.get("checkin_streak", 0),
        }
        for i, u in enumerate(top)
    ]


@app.get("/api/badges")
async def api_badges(user: dict = Depends(get_current_user)):
    """User badges + all available badges."""
    user_id = user["id"]
    info = get_points_info(user_id)
    user_badges = info.get("badges") or []

    all_badges = []
    for badge_id, badge_info in ACHIEVEMENTS.items():
        all_badges.append({
            "id": badge_id,
            "name": badge_info["name"],
            "emoji": badge_info["emoji"],
            "desc": badge_info["desc"],
            "unlocked": badge_id in user_badges,
        })

    return {"badges": all_badges, "unlocked_count": len(user_badges)}


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "ok"}

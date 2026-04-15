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
        await _ptb_app.bot.set_webhook(url=webhook_url, allowed_updates=["message", "callback_query", "my_chat_member"])
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

@app.get("/api/shop")
async def api_shop(user: dict = Depends(get_current_user)):
    """积分商城 — 按tier返回可见商品。"""
    from bot.handlers.points_shop import REWARDS_ALL, REWARDS_FREE, REWARDS_MEMBER, REWARDS_VIP
    user_id = user["id"]
    db = get_client()

    row = db.table("users").select("points, membership_tier, membership_status").eq("id", user_id).maybe_single().execute()
    u = row.data or {}
    points = u.get("points", 0) or 0
    tier = u.get("membership_tier", "free")
    if u.get("membership_status") == "admin":
        tier = "admin"

    sections = []
    sections.append({"title": "🔧 通用道具", "items": REWARDS_ALL})
    sections.append({"title": "🎁 好物兑换", "items": REWARDS_FREE})

    if tier in ("member", "vip", "admin"):
        sections.append({"title": "💎 会员专区", "items": REWARDS_MEMBER})
    if tier in ("vip", "admin"):
        sections.append({"title": "👑 私董会专区", "items": REWARDS_VIP})

    return {"points": points, "tier": tier, "sections": sections}


@app.post("/api/redeem")
async def api_redeem(request: Request, user: dict = Depends(get_current_user)):
    """积分兑换。"""
    from bot.handlers.points_shop import ALL_REWARDS, _can_access
    from db.points import redeem_points
    body = await request.json()
    reward_id = body.get("id", "")
    user_id = user["id"]

    reward = next((r for r in ALL_REWARDS if r["id"] == reward_id), None)
    if not reward:
        raise HTTPException(status_code=400, detail="Invalid reward")

    db = get_client()
    row = db.table("users").select("membership_tier, membership_status").eq("id", user_id).maybe_single().execute()
    u = row.data or {}
    tier = u.get("membership_tier", "free")
    if u.get("membership_status") == "admin":
        tier = "admin"

    if not _can_access(tier, reward["tier"]):
        raise HTTPException(status_code=403, detail="Tier too low")

    success = redeem_points(user_id, reward["cost"], reward["name"])
    if not success:
        raise HTTPException(status_code=400, detail="Insufficient points")

    # Get updated points
    info = db.table("users").select("points").eq("id", user_id).maybe_single().execute()
    new_points = (info.data or {}).get("points", 0)

    return {"success": True, "remaining_points": new_points, "reward": reward["name"]}


# ── H5 网页版 API (非 Telegram, 给微信/浏览器用) ──────────────────────────

from fastapi import Body
from webapp.h5_auth import generate_h5_token, verify_h5_token, get_h5_user
from db.users import get_user as _get_user_row
from db.points import get_points_info as _get_points
from services.claude_client import call_claude
from bot.handlers.daily_cognition import _TOPICS as COGNITION_TOPICS
from datetime import date as _date


@app.post("/api/h5/login")
async def h5_login(payload: dict = Body(...)):
    """H5 登录：用 token 换取 session cookie。"""
    token = (payload or {}).get("token", "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="缺少 token")

    user_id = verify_h5_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="token 无效或已过期")

    user = _get_user_row(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    resp = JSONResponse(content={
        "ok": True,
        "user": {
            "id": user_id,
            "name": user.get("full_name") or user.get("username") or str(user_id),
            "membership_status": user.get("membership_status", "free"),
            "membership_tier": user.get("membership_tier", "free"),
        },
    })
    resp.set_cookie(
        "h5_token", token,
        max_age=30 * 24 * 3600,
        httponly=True, secure=True, samesite="lax",
    )
    return resp


@app.post("/api/h5/logout")
async def h5_logout():
    resp = JSONResponse(content={"ok": True})
    resp.delete_cookie("h5_token")
    return resp


@app.get("/api/h5/me")
async def h5_me(user: dict = Depends(get_h5_user)):
    """H5 用户 Dashboard。"""
    user_id = user["id"]
    db = get_client()
    row = db.table("users").select(
        "points, checkin_streak, health_streak, gym_count, badges, "
        "membership_status, membership_tier, membership_expires_at, "
        "full_name, username"
    ).eq("id", user_id).maybe_single().execute()

    if not row or not row.data:
        raise HTTPException(status_code=404, detail="用户不存在")
    u = row.data

    # rank
    all_users = db.table("users").select("id").eq("is_active", True).gt("points", 0).order("points", desc=True).execute()
    rank = 0
    for i, r in enumerate(all_users.data or []):
        if r["id"] == user_id:
            rank = i + 1
            break

    return {
        "id": user_id,
        "name": u.get("full_name") or u.get("username") or str(user_id),
        "points": u.get("points", 0) or 0,
        "checkin_streak": u.get("checkin_streak", 0) or 0,
        "health_streak": u.get("health_streak", 0) or 0,
        "gym_count": u.get("gym_count", 0) or 0,
        "badges": u.get("badges") or [],
        "membership_status": u.get("membership_status", "free"),
        "membership_tier": u.get("membership_tier", "free"),
        "membership_expires_at": u.get("membership_expires_at"),
        "rank": rank,
    }


@app.get("/api/h5/cognition/today")
async def h5_cognition_today(user: dict = Depends(get_h5_user)):
    """获取今日认知话题。"""
    user_id = user["id"]
    idx = (user_id + _date.today().toordinal()) % len(COGNITION_TOPICS)
    t = COGNITION_TOPICS[idx]
    return {
        "title": t["title"],
        "desc": t["desc"],
        "question": t["question"],
    }


@app.post("/api/h5/cognition/submit")
async def h5_cognition_submit(
    payload: dict = Body(...),
    user: dict = Depends(get_h5_user),
):
    """提交认知训练回答，调用 Claude 点评。"""
    user_id = user["id"]
    reflection = (payload or {}).get("reflection", "").strip()
    if len(reflection) < 5:
        raise HTTPException(status_code=400, detail="回答太短了，至少写几句话")

    idx = (user_id + _date.today().toordinal()) % len(COGNITION_TOPICS)
    t = COGNITION_TOPICS[idx]

    user_input = (
        f"今日认知话题：{t['title']}\n"
        f"话题说明：{t['desc']}\n"
        f"思考题：{t['question']}\n\n"
        f"用户回答：{reflection}"
    )

    try:
        result = await call_claude("daily_cognition", user_input, user_id=user_id, max_tokens=600)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 处理失败: {str(e)[:100]}")

    # +5 积分
    try:
        db = get_client()
        urow = db.table("users").select("points").eq("id", user_id).maybe_single().execute()
        new_points = ((urow.data or {}).get("points", 0) or 0) + 5
        db.table("users").update({"points": new_points}).eq("id", user_id).execute()
    except Exception:
        new_points = None

    return {
        "feedback": result,
        "points_earned": 5,
        "total_points": new_points,
    }


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "ok"}

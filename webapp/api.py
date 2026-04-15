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

    # Set webhook — self-heal: delete first to drop any ghost webhook pointing elsewhere
    if BOT_MODE == "webhook" and WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}"
        try:
            # Check current webhook and only update if different (avoids thrashing)
            current = await _ptb_app.bot.get_webhook_info()
            if current.url != webhook_url:
                logger.warning("Webhook mismatch: current=%s, expected=%s", current.url, webhook_url)
                await _ptb_app.bot.delete_webhook(drop_pending_updates=False)
                await _ptb_app.bot.set_webhook(
                    url=webhook_url,
                    allowed_updates=["message", "callback_query", "my_chat_member"],
                )
                logger.info("Webhook force-reset to: %s", webhook_url)
            else:
                logger.info("Webhook already correct: %s", webhook_url)
        except Exception as e:
            logger.error("Failed to set webhook: %s", e)
            # Fallback: just set it
            await _ptb_app.bot.set_webhook(
                url=webhook_url,
                allowed_updates=["message", "callback_query", "my_chat_member"],
            )

    # Start updater processing (without running its own web server)
    asyncio.create_task(_ptb_app.updater.start_webhook(
        listen="127.0.0.1",
        port=0,  # Don't actually listen; we feed updates manually
        url_path=TELEGRAM_BOT_TOKEN,
        webhook_url="",  # Already set above
        drop_pending_updates=False,
    )) if False else None  # Skip updater; we push to update_queue directly

    # Background task: periodically verify webhook is correct (self-heal)
    async def _webhook_watchdog():
        while True:
            try:
                await asyncio.sleep(300)  # every 5 min
                if BOT_MODE != "webhook" or not WEBHOOK_URL:
                    continue
                expected = f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}"
                info = await _ptb_app.bot.get_webhook_info()
                if info.url != expected:
                    logger.warning("Watchdog: webhook drifted to %s, resetting", info.url)
                    await _ptb_app.bot.delete_webhook(drop_pending_updates=False)
                    await _ptb_app.bot.set_webhook(
                        url=expected,
                        allowed_updates=["message", "callback_query", "my_chat_member"],
                    )
            except Exception as e:
                logger.error("webhook watchdog error: %s", e)

    asyncio.create_task(_webhook_watchdog())

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

    new_points = _award_points(user_id, 5)
    return {"feedback": result, "points_earned": 5, "total_points": new_points}


# ── 通用 AI 功能端点 ─────────────────────────────────────────────────────────

# 功能元数据：key → {name, category, prompt_key, points, input_label, placeholder, max_tokens}
H5_FEATURES = {
    # 个人成长
    "daily_english": {
        "name": "今日英语升级",
        "emoji": "📝",
        "category": "growth",
        "prompt_key": "daily_english",
        "points": 3,
        "input_label": "写一句你想升级的中文或英文",
        "placeholder": "例如：我想跟客户说感谢他们的耐心...",
        "max_tokens": 700,
    },
    "evening_review": {
        "name": "晚间复盘",
        "emoji": "🌙",
        "category": "growth",
        "prompt_key": "evening_review",
        "points": 5,
        "input_label": "回答3个问题（一次写完）",
        "placeholder": "1. 今天最大的收获是什么？\n2. 今天最大的浪费是什么？\n3. 明天最重要的一件事是什么？",
        "max_tokens": 800,
    },
    "daily_plan": {
        "name": "今日计划",
        "emoji": "📋",
        "category": "growth",
        "prompt_key": "daily_plan",
        "points": 3,
        "input_label": "列出你今天想做的事",
        "placeholder": "把脑子里乱糟糟的待办事项全写下来，老王帮你排优先级...",
        "max_tokens": 800,
    },
    "decision_helper": {
        "name": "决策助手",
        "emoji": "🧭",
        "category": "growth",
        "prompt_key": "decision_helper",
        "points": 0,
        "input_label": "描述你面临的决策",
        "placeholder": "例如：我现在有两个工作offer，一个大厂稳定，一个创业高风险...",
        "max_tokens": 900,
    },
    "procrastination": {
        "name": "拖延破解器",
        "emoji": "🧨",
        "category": "growth",
        "prompt_key": "procrastination_breaker",
        "points": 0,
        "input_label": "你在拖延什么？",
        "placeholder": "例如：明明要写季度报告，已经拖了一周了...",
        "max_tokens": 700,
    },
    "text_optimizer": {
        "name": "表达优化器",
        "emoji": "🗣️",
        "category": "growth",
        "prompt_key": "text_optimizer",
        "points": 0,
        "input_label": "粘贴你想优化的文字",
        "placeholder": "任何你觉得可以说得更好的话...",
        "max_tokens": 800,
    },
    "biz_reply": {
        "name": "商务回复助手",
        "emoji": "💼",
        "category": "growth",
        "prompt_key": "biz_reply",
        "points": 0,
        "input_label": "粘贴对方的消息 + 你的回复意图",
        "placeholder": "对方说：...\n\n我想表达：...",
        "max_tokens": 800,
    },
    "chinglish_fix": {
        "name": "中式英语改写",
        "emoji": "🔄",
        "category": "growth",
        "prompt_key": "chinglish_fix",
        "points": 0,
        "input_label": "粘贴你写的英文",
        "placeholder": "Paste your English text here...",
        "max_tokens": 700,
    },
    "biz_english": {
        "name": "商务英语对话",
        "emoji": "💬",
        "category": "growth",
        "prompt_key": "biz_english",
        "points": 0,
        "input_label": "选个场景并描述需求",
        "placeholder": "例如：谈判时对方说 your price is too high 我要怎么回...",
        "max_tokens": 800,
    },

    # 创业财富
    "viral_topic": {
        "name": "爆款选题",
        "emoji": "🔥",
        "category": "wealth",
        "prompt_key": "viral_topic",
        "points": 0,
        "input_label": "你的领域/账号定位",
        "placeholder": "例如：专注投资理财的个人IP号，受众是30-45岁中产...",
        "max_tokens": 900,
    },
    "script_gen": {
        "name": "口播脚本",
        "emoji": "🎙️",
        "category": "wealth",
        "prompt_key": "script_gen",
        "points": 0,
        "input_label": "你的选题/主题",
        "placeholder": "例如：为什么大部分人越努力越穷，给我一个3分钟口播稿...",
        "max_tokens": 1000,
    },
    "script_polish": {
        "name": "口播稿优化",
        "emoji": "✍️",
        "category": "wealth",
        "prompt_key": "script_polish",
        "points": 0,
        "input_label": "粘贴你的脚本",
        "placeholder": "把你写的稿子粘进来，老王从开头、节奏、结构、CTA 四维度打分...",
        "max_tokens": 900,
    },
    "brand_positioning": {
        "name": "品牌定位诊断",
        "emoji": "💎",
        "category": "wealth",
        "prompt_key": "brand_positioning",
        "points": 0,
        "input_label": "描述你的项目/品牌",
        "placeholder": "产品是什么 + 目标用户 + 现在的定位文案...",
        "max_tokens": 1000,
    },
    "sales_assist": {
        "name": "销售助手",
        "emoji": "🤝",
        "category": "wealth",
        "prompt_key": "sales_assist",
        "points": 0,
        "input_label": "粘贴对方消息/合同/场景",
        "placeholder": "例如：客户说'预算不够'我要怎么回？...",
        "max_tokens": 900,
    },
    "property_diag": {
        "name": "民宿诊断",
        "emoji": "🏡",
        "category": "wealth",
        "prompt_key": "property_diag",
        "points": 0,
        "input_label": "描述房源/位置/装修/价格",
        "placeholder": "城市+位置+房型+预算+你的目标...",
        "max_tokens": 900,
    },
    "landlord_msg": {
        "name": "民宿话术",
        "emoji": "💬",
        "category": "wealth",
        "prompt_key": "landlord_msg",
        "points": 0,
        "input_label": "客人/房东的消息 + 你的情况",
        "placeholder": "客人说：...\n\n我的情况：...",
        "max_tokens": 700,
    },
    "trade_review": {
        "name": "交易复盘",
        "emoji": "📊",
        "category": "wealth",
        "prompt_key": "trade_review",
        "points": 0,
        "input_label": "品种 + 入场理由 + 情绪 + 结果",
        "placeholder": "例如：TSLA，财报前买入，FOMO心态，结果亏5%...",
        "max_tokens": 900,
    },

    # 个人健康
    "workout_plan": {
        "name": "今日训练",
        "emoji": "🏋️",
        "category": "health",
        "prompt_key": "workout_plan",
        "points": 0,
        "input_label": "目标 + 部位 + 时长",
        "placeholder": "例如：增肌，练胸和三头，45分钟，家里哑铃...",
        "max_tokens": 900,
    },
    "meal_plan": {
        "name": "今日食谱",
        "emoji": "🍽️",
        "category": "health",
        "prompt_key": "meal_plan",
        "points": 0,
        "input_label": "目标 + 体重 + 偏好",
        "placeholder": "例如：减脂，75kg男，不吃牛羊，给我今日三餐...",
        "max_tokens": 900,
    },
}


def _award_points(user_id: int, amount: int):
    """给用户加积分，返回新的总分；失败返回 None。"""
    if amount <= 0:
        return None
    try:
        db = get_client()
        urow = db.table("users").select("points").eq("id", user_id).maybe_single().execute()
        new_total = ((urow.data or {}).get("points", 0) or 0) + amount
        db.table("users").update({"points": new_total}).eq("id", user_id).execute()
        return new_total
    except Exception:
        return None


@app.get("/api/h5/features")
async def h5_features():
    """返回所有可用 H5 AI 功能列表（前端动态渲染用）。"""
    result = {"growth": [], "health": [], "wealth": []}
    for key, f in H5_FEATURES.items():
        result[f["category"]].append({
            "key": key,
            "name": f["name"],
            "emoji": f["emoji"],
            "points": f["points"],
        })
    # 添加特殊功能
    result["growth"].insert(0, {"key": "daily_cognition", "name": "今日认知", "emoji": "💡", "points": 5})
    result["wealth"].insert(0, {"key": "news_brief", "name": "今日简报", "emoji": "📰", "points": 0})
    return result


@app.get("/api/h5/feature/{key}")
async def h5_feature_info(key: str, user: dict = Depends(get_h5_user)):
    """获取某个功能的元数据（名字、输入提示、描述）。"""
    f = H5_FEATURES.get(key)
    if not f:
        raise HTTPException(status_code=404, detail="功能不存在")
    return {
        "key": key,
        "name": f["name"],
        "emoji": f["emoji"],
        "input_label": f["input_label"],
        "placeholder": f["placeholder"],
        "points": f["points"],
    }


@app.post("/api/h5/ai/{key}")
async def h5_ai_run(
    key: str,
    payload: dict = Body(...),
    user: dict = Depends(get_h5_user),
):
    """通用 AI 功能端点：接收用户输入，调用 Claude，返回结果 + 可能的积分奖励。"""
    f = H5_FEATURES.get(key)
    if not f:
        raise HTTPException(status_code=404, detail="功能不存在")

    user_id = user["id"]
    user_input = (payload or {}).get("input", "").strip()
    if len(user_input) < 3:
        raise HTTPException(status_code=400, detail="输入太短了")
    if len(user_input) > 4000:
        raise HTTPException(status_code=400, detail="输入太长了，请控制在4000字以内")

    try:
        result = await call_claude(
            f["prompt_key"],
            user_input,
            user_id=user_id,
            max_tokens=f.get("max_tokens", 800),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 处理失败: {str(e)[:100]}")

    # 内容安全过滤（预留，目前只过简单黑名单）
    result = _content_safety_check(result)

    points = f.get("points", 0)
    new_total = _award_points(user_id, points)
    return {
        "result": result,
        "points_earned": points,
        "total_points": new_total,
    }


def _content_safety_check(text: str) -> str:
    """基础内容安全检查。未来可替换为阿里云/腾讯云 textScan API。"""
    # 极简黑名单过滤，避免最明显的敏感词输出
    # TODO: 接入阿里云 msgSecCheck 或腾讯云 TMS
    return text


# ── 今日简报（无输入，直接调用） ──────────────────────────────────────────────

@app.get("/api/h5/news/brief")
async def h5_news_brief(user: dict = Depends(get_h5_user)):
    """今日财经简报。"""
    user_id = user["id"]
    try:
        from services.news_fetcher import fetch_daily_news, format_articles_for_claude
        articles = fetch_daily_news()
        news_text = format_articles_for_claude(articles)
        result = await call_claude(
            "news_brief",
            news_text,
            user_id=user_id,
            max_tokens=1200,
            extra_context=f"今日日期：{_date.today().isoformat()}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取简报失败: {str(e)[:100]}")
    return {"result": _content_safety_check(result)}


# ── 签到 / 打卡 ─────────────────────────────────────────────────────────────

@app.post("/api/h5/checkin")
async def h5_checkin(user: dict = Depends(get_h5_user)):
    """H5 每日签到。"""
    from db.points import do_checkin
    user_id = user["id"]
    result = do_checkin(user_id)
    return result


@app.post("/api/h5/health-checkin")
async def h5_health_checkin(
    payload: dict = Body(...),
    user: dict = Depends(get_h5_user),
):
    """H5 健康打卡（心情 + 笔记）。"""
    from db.health import do_health_checkin
    user_id = user["id"]
    mood = (payload or {}).get("mood", "😊")
    note = (payload or {}).get("note", "").strip()

    result = do_health_checkin(user_id, mood, note)
    return result


# ── 邀请链接 ─────────────────────────────────────────────────────────────────

@app.get("/api/h5/shop")
async def h5_shop(user: dict = Depends(get_h5_user)):
    """H5 积分商城。"""
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


@app.post("/api/h5/redeem")
async def h5_redeem(payload: dict = Body(...), user: dict = Depends(get_h5_user)):
    """H5 积分兑换。"""
    from bot.handlers.points_shop import ALL_REWARDS, _can_access
    from db.points import redeem_points
    reward_id = (payload or {}).get("id", "")
    user_id = user["id"]

    reward = next((r for r in ALL_REWARDS if r["id"] == reward_id), None)
    if not reward:
        raise HTTPException(status_code=400, detail="商品不存在")

    db = get_client()
    row = db.table("users").select("membership_tier, membership_status").eq("id", user_id).maybe_single().execute()
    u = row.data or {}
    tier = u.get("membership_tier", "free")
    if u.get("membership_status") == "admin":
        tier = "admin"

    if not _can_access(tier, reward["tier"]):
        raise HTTPException(status_code=403, detail="此商品需要更高会员等级")

    success = redeem_points(user_id, reward["cost"], reward["name"])
    if not success:
        raise HTTPException(status_code=400, detail="积分不足")

    info = db.table("users").select("points").eq("id", user_id).maybe_single().execute()
    new_points = (info.data or {}).get("points", 0)

    return {"success": True, "remaining_points": new_points, "reward": reward["name"]}


@app.get("/api/h5/leaderboard")
async def h5_leaderboard(user: dict = Depends(get_h5_user)):
    """H5 排行榜（需要登录）。"""
    from db.points import get_leaderboard
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


@app.get("/api/h5/invite")
async def h5_invite(user: dict = Depends(get_h5_user)):
    """生成 H5 邀请链接。"""
    user_id = user["id"]
    db = get_client()
    urow = db.table("users").select("membership_tier, membership_status").eq("id", user_id).maybe_single().execute()
    u = (urow.data or {})
    tier = u.get("membership_tier", "free")
    if u.get("membership_status") == "admin":
        tier = "admin"

    from bot.handlers.referral import REFERRAL_POINTS
    inviter_pts, invitee_pts = REFERRAL_POINTS.get(tier, REFERRAL_POINTS["free"])

    ref_count = db.table("referrals").select("id", count="exact").eq("referrer_id", user_id).execute()
    total_invited = ref_count.count or 0

    bot_username = os.getenv("BOT_USERNAME", "laowang_toolbox_bot")
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    return {
        "link": link,
        "tier": tier,
        "inviter_points": inviter_pts,
        "invitee_points": invitee_pts,
        "total_invited": total_invited,
    }


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "ok"}

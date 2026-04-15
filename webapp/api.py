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
    """返回所有可用 H5 功能列表（AI + 静态 + 打卡 + 工具）。"""
    # type: ai_input (generic AI) / special (自定义页面) / static (静态内容) / tool / checkin
    result = {"growth": [], "health": [], "wealth": []}

    # 添加所有 AI 输入型功能
    for key, f in H5_FEATURES.items():
        result[f["category"]].append({
            "key": key,
            "name": f["name"],
            "emoji": f["emoji"],
            "points": f["points"],
            "type": "ai_input",
        })

    # 添加特殊功能（有自定义页面的）
    special = {
        "growth": [
            {"key": "daily_cognition", "name": "今日认知", "emoji": "💡", "points": 5, "type": "special"},
            {"key": "deep_work", "name": "深度工作打卡", "emoji": "🔥", "points": 10, "type": "special"},
        ],
        "wealth": [
            {"key": "news_brief", "name": "今日简报", "emoji": "📰", "points": 0, "type": "special"},
            {"key": "premarket", "name": "盘前情报", "emoji": "📊", "points": 0, "type": "special"},
            {"key": "postmarket", "name": "盘后复盘", "emoji": "📉", "points": 0, "type": "special"},
            {"key": "portfolio", "name": "老王持仓", "emoji": "💡", "points": 0, "type": "special"},
            {"key": "strategy", "name": "投资策略", "emoji": "📋", "points": 0, "type": "static"},
            {"key": "us_stock", "name": "美股开户教程", "emoji": "🏦", "points": 0, "type": "static"},
        ],
        "health": [
            {"key": "gym_log", "name": "健身打卡", "emoji": "🏃", "points": 8, "type": "special"},
            {"key": "protein_calc", "name": "蛋白质计算", "emoji": "🧮", "points": 0, "type": "tool"},
            {"key": "calorie_calc", "name": "卡路里计算", "emoji": "🔥", "points": 0, "type": "tool"},
            {"key": "snacks", "name": "零食白名单", "emoji": "🍫", "points": 0, "type": "static"},
            {"key": "supplements", "name": "老王补给", "emoji": "💊", "points": 0, "type": "static"},
            {"key": "plans", "name": "老王计划库", "emoji": "💪", "points": 0, "type": "special"},
        ],
    }

    for cat in ["growth", "wealth", "health"]:
        for item in special.get(cat, []):
            result[cat].insert(0, item) if item["type"] == "special" else result[cat].append(item)

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


# ── 盘前盘后情报 ────────────────────────────────────────────────────────────

@app.get("/api/h5/premarket")
async def h5_premarket(user: dict = Depends(get_h5_user)):
    """盘前情报（抓数据 + AI 分析）。"""
    from services.market_data import get_market_snapshot, format_snapshot_for_claude
    from datetime import datetime
    user_id = user["id"]
    try:
        snapshot = get_market_snapshot()
        market_text = format_snapshot_for_claude(snapshot)
        date_str = datetime.now().strftime("%Y年%m月%d日")
        result = await call_claude(
            "market_intel_pre",
            market_text,
            user_id=user_id,
            max_tokens=900,
            extra_context=f"当前时间（美东）：{date_str}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取盘前情报失败: {str(e)[:100]}")
    return {"result": _content_safety_check(result)}


@app.get("/api/h5/postmarket")
async def h5_postmarket(user: dict = Depends(get_h5_user)):
    """盘后复盘。"""
    from services.market_data import get_market_snapshot, format_snapshot_for_claude
    from datetime import datetime
    user_id = user["id"]
    try:
        snapshot = get_market_snapshot()
        market_text = format_snapshot_for_claude(snapshot)
        date_str = datetime.now().strftime("%Y年%m月%d日")
        result = await call_claude(
            "market_intel_post",
            market_text,
            user_id=user_id,
            max_tokens=900,
            extra_context=f"当前时间（美东）：{date_str}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取盘后复盘失败: {str(e)[:100]}")
    return {"result": _content_safety_check(result)}


# ── 老王持仓 (按tier显示) ──────────────────────────────────────────────────

@app.get("/api/h5/portfolio")
async def h5_portfolio(user: dict = Depends(get_h5_user)):
    """老王持仓 — 按tier分层返回。"""
    from bot.handlers.wealth_static import _FULL_PORTFOLIO, _FREE_COUNT
    user_id = user["id"]
    db = get_client()
    urow = db.table("users").select("membership_tier, membership_status").eq("id", user_id).maybe_single().execute()
    u = (urow.data or {})
    tier = u.get("membership_tier", "free")
    if u.get("membership_status") == "admin":
        tier = "admin"

    if tier in ("vip", "admin"):
        # 完整持仓 + 最近信号
        stocks = _FULL_PORTFOLIO
        signals = db.table("trade_signals").select("*").order("created_at", desc=True).limit(5).execute()
        return {
            "tier": tier,
            "stocks": stocks,
            "signals": signals.data or [],
            "is_full": True,
        }
    elif tier == "member":
        return {
            "tier": tier,
            "stocks": _FULL_PORTFOLIO,
            "signals": [],
            "is_full": True,
            "note": "升级私董会可查看实时持仓 + 每笔交易推送",
        }
    else:
        return {
            "tier": tier,
            "stocks": _FULL_PORTFOLIO[:_FREE_COUNT],
            "signals": [],
            "is_full": False,
            "locked_count": len(_FULL_PORTFOLIO) - _FREE_COUNT,
            "note": "开通会员查看全部持仓",
        }


# ── 静态内容端点 ──────────────────────────────────────────────────────────────

@app.get("/api/h5/content/{key}")
async def h5_content(key: str, user: dict = Depends(get_h5_user)):
    """静态内容端点：strategy/us_stock/snacks/supplements/membership/plans"""
    from webapp import h5_content as hc
    mapping = {
        "strategy": {"title": "📋 老王投资策略", "text": hc.STRATEGY_TEXT},
        "us_stock": {"title": "🏦 美股开户教程", "text": hc.US_STOCK_TEXT},
        "snacks": {"title": "🍫 零食白名单", "text": hc.SNACKS_TEXT},
        "supplements": {"title": "💊 老王补给", "text": hc.SUPPLEMENTS_TEXT},
    }
    if key in mapping:
        return mapping[key]
    if key == "membership":
        return {"title": "💎 会员权益", "data": hc.MEMBERSHIP_INFO}
    if key == "plans":
        return {"title": "💪 老王计划库", "plans": hc.WANG_PLANS}
    raise HTTPException(status_code=404, detail="内容不存在")


# ── 计算器 ──────────────────────────────────────────────────────────────────

@app.post("/api/h5/calc/protein")
async def h5_calc_protein(payload: dict = Body(...), user: dict = Depends(get_h5_user)):
    """蛋白质计算器。"""
    weight = float((payload or {}).get("weight", 0))
    goal = (payload or {}).get("goal", "maintain")  # lose/maintain/gain
    activity = (payload or {}).get("activity", "mid")  # low/mid/high
    if weight <= 0:
        raise HTTPException(status_code=400, detail="体重必须大于0")

    # 每 kg 蛋白质需要
    multipliers = {
        ("lose", "low"): 1.6,
        ("lose", "mid"): 1.8,
        ("lose", "high"): 2.2,
        ("maintain", "low"): 1.2,
        ("maintain", "mid"): 1.6,
        ("maintain", "high"): 1.8,
        ("gain", "low"): 1.6,
        ("gain", "mid"): 1.8,
        ("gain", "high"): 2.2,
    }
    mult = multipliers.get((goal, activity), 1.6)
    daily_g = round(weight * mult)

    return {
        "daily_grams": daily_g,
        "per_meal_3": round(daily_g / 3),
        "per_meal_4": round(daily_g / 4),
        "sources": [
            f"鸡胸肉 {round(daily_g / 0.23)}g（约 {round(daily_g / 0.23 / 100, 1)} 份）",
            f"鸡蛋 {round(daily_g / 6)} 个",
            f"蛋白粉 {round(daily_g / 25)} 勺（每勺25g）",
            f"牛肉 {round(daily_g / 0.26)}g",
            f"鱼肉 {round(daily_g / 0.22)}g",
        ],
        "tip": "训练日可加10-20%，休息日按此数。优先真食物 > 蛋白粉。",
    }


@app.post("/api/h5/calc/calorie")
async def h5_calc_calorie(payload: dict = Body(...), user: dict = Depends(get_h5_user)):
    """卡路里计算器 (Mifflin-St Jeor)。"""
    weight = float((payload or {}).get("weight", 0))
    height = float((payload or {}).get("height", 0))
    age = int((payload or {}).get("age", 0))
    gender = (payload or {}).get("gender", "male")  # male/female
    activity = (payload or {}).get("activity", "mid")  # low/mid/high/very_high
    goal = (payload or {}).get("goal", "maintain")

    if weight <= 0 or height <= 0 or age <= 0:
        raise HTTPException(status_code=400, detail="请填写完整的体重/身高/年龄")

    # BMR (Mifflin-St Jeor)
    if gender == "male":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    # TDEE
    factors = {"low": 1.2, "mid": 1.55, "high": 1.725, "very_high": 1.9}
    tdee = bmr * factors.get(activity, 1.55)

    # 目标调整
    target = tdee
    if goal == "lose": target = tdee - 500
    elif goal == "gain": target = tdee + 300

    return {
        "bmr": round(bmr),
        "tdee": round(tdee),
        "target": round(target),
        "macros": {
            "protein_g": round(weight * 1.8),
            "fat_g": round(target * 0.25 / 9),
            "carbs_g": round((target - weight * 1.8 * 4 - target * 0.25) / 4),
        },
        "tip": f"目标: {'减脂' if goal == 'lose' else '增肌' if goal == 'gain' else '维持'} - 每日约 {round(target)} 大卡",
    }


# ── 健身打卡 ────────────────────────────────────────────────────────────────

@app.post("/api/h5/gym-log")
async def h5_gym_log(payload: dict = Body(...), user: dict = Depends(get_h5_user)):
    """健身打卡记录。"""
    from db.health import do_gym_log
    user_id = user["id"]
    workout_type = (payload or {}).get("workout_type", "全身")
    duration = int((payload or {}).get("duration_min", 30))
    intensity = int((payload or {}).get("intensity", 3))
    notes = (payload or {}).get("notes", "").strip()

    if duration <= 0 or duration > 300:
        raise HTTPException(status_code=400, detail="训练时长应在1-300分钟之间")
    if intensity < 1 or intensity > 5:
        raise HTTPException(status_code=400, detail="强度必须为1-5")

    result = do_gym_log(user_id, workout_type, duration, intensity, notes)
    return result


# ── 深度工作打卡 ──────────────────────────────────────────────────────────────

@app.post("/api/h5/deep-work")
async def h5_deep_work(payload: dict = Body(...), user: dict = Depends(get_h5_user)):
    """深度工作打卡 — 记录一次专注时段。"""
    user_id = user["id"]
    duration = int((payload or {}).get("duration_min", 0))
    task = (payload or {}).get("task", "").strip()

    if duration <= 0:
        raise HTTPException(status_code=400, detail="时长必须大于0")

    # 按时长给分: 25分=+5, 60分=+10, 90分+=+15
    if duration >= 90:
        points = 15
    elif duration >= 60:
        points = 10
    elif duration >= 25:
        points = 5
    else:
        points = 2

    new_total = _award_points(user_id, points)
    return {
        "success": True,
        "points_earned": points,
        "total_points": new_total,
        "duration_min": duration,
        "task": task,
    }


# ── 成绩单 (用户综合数据) ────────────────────────────────────────────────────

@app.get("/api/h5/report")
async def h5_report(user: dict = Depends(get_h5_user)):
    """用户综合成绩单：积分+连续+健身+健康+AI次数。"""
    user_id = user["id"]
    db = get_client()
    urow = db.table("users").select(
        "points, checkin_streak, health_streak, gym_count, badges, full_name, username"
    ).eq("id", user_id).maybe_single().execute()
    u = urow.data or {}

    # 本月统计
    from datetime import datetime
    month_start = datetime.now().replace(day=1).date().isoformat()
    checkins = db.table("checkin_logs").select("id", count="exact").eq("user_id", user_id).gte("checkin_date", month_start).execute()
    gym_logs = db.table("gym_logs").select("id", count="exact").eq("user_id", user_id).gte("log_date", month_start).execute()
    health_logs = db.table("health_checkins").select("id", count="exact").eq("user_id", user_id).gte("checkin_date", month_start).execute()

    # 今日AI使用次数
    today = _date.today().isoformat()
    ai_logs = db.table("usage_logs").select("id", count="exact").eq("user_id", user_id).gte("created_at", f"{today}T00:00:00").execute()

    return {
        "name": u.get("full_name") or u.get("username") or str(user_id),
        "points": u.get("points", 0) or 0,
        "checkin_streak": u.get("checkin_streak", 0) or 0,
        "health_streak": u.get("health_streak", 0) or 0,
        "gym_count": u.get("gym_count", 0) or 0,
        "badges_count": len(u.get("badges") or []),
        "this_month": {
            "checkins": checkins.count or 0,
            "gym": gym_logs.count or 0,
            "health": health_logs.count or 0,
        },
        "today_ai_calls": ai_logs.count or 0,
    }


# ── 徽章成就 ────────────────────────────────────────────────────────────────

@app.get("/api/h5/badges")
async def h5_badges(user: dict = Depends(get_h5_user)):
    """用户成就徽章（区分已解锁/未解锁）。"""
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
    return {"badges": all_badges, "unlocked_count": len(user_badges), "total": len(all_badges)}


@app.get("/api/h5/consult/packages")
async def h5_consult_packages(user: dict = Depends(get_h5_user)):
    """咨询套餐列表。"""
    from bot.handlers.consultation import PACKAGES
    items = []
    for key, pkg in PACKAGES.items():
        items.append({
            "key": key,
            "name": pkg["name"],
            "duration": pkg["duration"],
            "price": pkg["price"],
            "desc": pkg["desc"],
            "tag": pkg.get("tag", ""),
        })
    return {"packages": items}


@app.post("/api/h5/consult/book")
async def h5_consult_book(payload: dict = Body(...), user: dict = Depends(get_h5_user)):
    """提交咨询预约 + 通知管理员。"""
    from bot.handlers.consultation import PACKAGES
    from db.users import get_admin_ids
    from datetime import datetime, timezone

    user_id = user["id"]
    package_key = (payload or {}).get("package", "")
    topic = (payload or {}).get("topic", "").strip()

    if package_key not in PACKAGES:
        raise HTTPException(status_code=400, detail="套餐无效")
    if len(topic) < 5:
        raise HTTPException(status_code=400, detail="咨询主题至少5个字")
    if len(topic) > 1000:
        raise HTTPException(status_code=400, detail="咨询主题太长了")

    pkg = PACKAGES[package_key]
    db = get_client()

    try:
        db.table("consultation_bookings").insert({
            "user_id": user_id,
            "package": package_key,
            "topic": topic,
            "status": "pending",
        }).execute()
    except Exception as e:
        logger.warning("Failed to save booking: %s", e)

    u = db.table("users").select("full_name, username").eq("id", user_id).maybe_single().execute()
    u_data = u.data or {}
    name = u_data.get("full_name") or u_data.get("username") or str(user_id)
    uname = f"@{u_data.get('username')}" if u_data.get("username") else "无用户名"

    admin_text = (
        f"🔔 *新咨询预约 (H5)*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 用户：{name}（{uname}）\n"
        f"🆔 ID：`{user_id}`\n"
        f"📦 套餐：{pkg['name']}\n"
        f"⏱ 时长：{pkg['duration']}\n"
        f"💰 费用：{pkg['price']}\n\n"
        f"💬 *咨询主题：*\n_{topic}_\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    if _ptb_app:
        for admin_id in get_admin_ids():
            try:
                await _ptb_app.bot.send_message(
                    chat_id=admin_id, text=admin_text, parse_mode="Markdown",
                )
            except Exception as e:
                logger.warning("Failed to notify admin %s: %s", admin_id, e)

    return {"success": True, "package_name": pkg["name"], "price": pkg["price"]}


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

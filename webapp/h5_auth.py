"""
H5 网页端身份认证（无状态 HMAC 签名 token）
不依赖 Telegram initData，适用于微信浏览器/普通手机浏览器访问。

Token 格式: base64url(user_id).base64url(exp).base64url(hmac)
"""
import base64
import hashlib
import hmac
import time
from typing import Optional

from fastapi import HTTPException, Request, Depends

from config.settings import TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY

# 用 bot token 衍生 H5 session 密钥，不暴露原始 token
_SECRET = hashlib.sha256((TELEGRAM_BOT_TOKEN + "h5_session_v1").encode()).digest()

# H5 session 默认 30 天有效
_DEFAULT_TTL_SECONDS = 30 * 24 * 3600


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def generate_h5_token(user_id: int, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> str:
    """为用户生成一个可在 H5 中使用的登录 token。"""
    exp = int(time.time()) + ttl_seconds
    uid_b = str(user_id).encode()
    exp_b = str(exp).encode()
    payload = uid_b + b"." + exp_b
    sig = hmac.new(_SECRET, payload, hashlib.sha256).digest()
    return f"{_b64e(uid_b)}.{_b64e(exp_b)}.{_b64e(sig)}"


def verify_h5_token(token: str) -> Optional[int]:
    """验证 token 并返回 user_id。无效/过期返回 None。"""
    try:
        uid_part, exp_part, sig_part = token.split(".")
        uid_b = _b64d(uid_part)
        exp_b = _b64d(exp_part)
        sig = _b64d(sig_part)
    except Exception:
        return None

    payload = uid_b + b"." + exp_b
    expected = hmac.new(_SECRET, payload, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, sig):
        return None

    try:
        exp = int(exp_b)
        user_id = int(uid_b)
    except ValueError:
        return None

    if time.time() > exp:
        return None

    return user_id


async def get_h5_user(request: Request) -> dict:
    """FastAPI dependency: 从 Cookie 或 Authorization header 中获取 H5 用户。"""
    token = request.cookies.get("h5_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]

    if not token:
        raise HTTPException(status_code=401, detail="未登录")

    user_id = verify_h5_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="登录已过期或 token 无效")

    return {"id": user_id}

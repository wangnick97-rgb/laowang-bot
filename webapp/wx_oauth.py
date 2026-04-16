"""
微信公众号网页授权 OAuth 2.0 登录
流程:
1. H5 检测未登录 + 在微信浏览器内 → 重定向到微信授权页
2. 微信回调 /api/wx/callback?code=xxx → 后端用 code 换 openid
3. 后端查找/创建用户 → 生成 H5 token → 重定向回 H5 并自动登录
"""
import os
import logging
import httpx
from urllib.parse import quote

from db.client import get_client
from db.users import get_user, upsert_user
from webapp.h5_auth import generate_h5_token

logger = logging.getLogger(__name__)

WX_APPID = os.getenv("WX_APPID", "")
WX_APPSECRET = os.getenv("WX_APPSECRET", "")


def get_oauth_url(redirect_uri: str, state: str = "") -> str:
    """生成微信 OAuth 授权 URL (snsapi_base 静默授权)。"""
    return (
        f"https://open.weixin.qq.com/connect/oauth2/authorize"
        f"?appid={WX_APPID}"
        f"&redirect_uri={quote(redirect_uri)}"
        f"&response_type=code"
        f"&scope=snsapi_base"
        f"&state={state}"
        f"#wechat_redirect"
    )


async def code_to_openid(code: str) -> dict | None:
    """用 code 换取 openid + access_token。"""
    url = (
        f"https://api.weixin.qq.com/sns/oauth2/access_token"
        f"?appid={WX_APPID}"
        f"&secret={WX_APPSECRET}"
        f"&code={code}"
        f"&grant_type=authorization_code"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10)
        data = resp.json()

    if "openid" not in data:
        logger.warning("WeChat OAuth failed: %s", data)
        return None

    return data  # {access_token, openid, ...}


def find_or_create_wx_user(openid: str) -> int:
    """通过 wx_openid 查找用户，没有就创建新用户。返回 user_id。"""
    db = get_client()

    # 先查有没有已绑定此 openid 的用户
    result = db.table("users").select("id").eq("wx_openid", openid).maybe_single().execute()
    if result and result.data:
        return result.data["id"]

    # 没有 → 创建新用户（用 openid hash 做临时 ID）
    import hashlib
    # 生成一个稳定的数字 ID（基于 openid 的 hash，取前 10 位数字）
    hash_int = int(hashlib.sha256(openid.encode()).hexdigest()[:12], 16) % (10**10)
    # 确保不与现有 ID 冲突
    existing = db.table("users").select("id").eq("id", hash_int).maybe_single().execute()
    if existing and existing.data:
        hash_int = hash_int + 1  # 极小概率冲突，简单+1

    db.table("users").upsert({
        "id": hash_int,
        "wx_openid": openid,
        "username": f"wx_{openid[:8]}",
        "full_name": "微信用户",
        "membership_status": "free",
        "is_active": True,
        "points": 0,
    }, on_conflict="id").execute()

    return hash_int

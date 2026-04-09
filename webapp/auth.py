"""
Telegram Mini App initData validation.
HMAC-SHA256 verification as per https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, unquote

from fastapi import HTTPException, Request

from config.settings import TELEGRAM_BOT_TOKEN

# initData is valid for 1 hour
_MAX_AGE_SECONDS = 3600


def validate_init_data(init_data: str) -> dict:
    """Validate Telegram WebApp initData and return user info."""
    parsed = parse_qs(init_data, keep_blank_values=True)

    # Extract hash
    received_hash = parsed.get("hash", [None])[0]
    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing hash")

    # Build data-check-string: sort all params except hash, join with \n
    check_pairs = []
    for key in sorted(parsed.keys()):
        if key == "hash":
            continue
        check_pairs.append(f"{key}={parsed[key][0]}")
    data_check_string = "\n".join(check_pairs)

    # Compute HMAC
    secret_key = hmac.new(b"WebAppData", TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid hash")

    # Check auth_date freshness
    auth_date = int(parsed.get("auth_date", [0])[0])
    if time.time() - auth_date > _MAX_AGE_SECONDS:
        raise HTTPException(status_code=401, detail="initData expired")

    # Extract user
    user_raw = parsed.get("user", [None])[0]
    if not user_raw:
        raise HTTPException(status_code=401, detail="No user data")

    user = json.loads(unquote(user_raw))
    return user


async def get_current_user(request: Request) -> dict:
    """FastAPI dependency: extract and validate Telegram user from initData header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("tma "):
        raise HTTPException(status_code=401, detail="Missing Authorization: tma <initData>")
    init_data = auth[4:]
    return validate_init_data(init_data)

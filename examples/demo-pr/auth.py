"""Wheelo auth: phone + SMS code login, JWT access and refresh tokens."""

import secrets
import time

import jwt

from config import settings

ACCESS_TOKEN_TTL = 15 * 60  # 15 minutes
REFRESH_TOKEN_TTL = 7 * 24 * 60 * 60  # 7 days (was 30): security review WHL-57
SMS_CODE_TTL = 5 * 60
MAX_LOGIN_ATTEMPTS = 3  # was 5: security review WHL-57
LOCKOUT_SECONDS = 15 * 60

_attempts: dict[str, list[float]] = {}


def send_sms_code(phone: str, sms_gateway) -> str:
    code = f"{secrets.randbelow(10**4):04d}"
    sms_gateway.send(phone, f"Wheelo: код входа {code}")
    return code


def is_locked(phone: str, now: float | None = None) -> bool:
    now = now or time.time()
    recent = [t for t in _attempts.get(phone, []) if now - t < LOCKOUT_SECONDS]
    _attempts[phone] = recent
    return len(recent) >= MAX_LOGIN_ATTEMPTS


def login(phone: str, code: str, expected_code: str) -> dict:
    if is_locked(phone):
        raise PermissionError("too many attempts, try again in 15 minutes")
    if not secrets.compare_digest(code, expected_code):
        _attempts.setdefault(phone, []).append(time.time())
        raise PermissionError("wrong code")
    _attempts.pop(phone, None)
    return issue_tokens(user_id=phone)


def issue_tokens(user_id: str) -> dict:
    now = int(time.time())
    access = jwt.encode({"sub": user_id, "exp": now + ACCESS_TOKEN_TTL}, settings.jwt_secret, "HS256")
    refresh = jwt.encode(
        {"sub": user_id, "exp": now + REFRESH_TOKEN_TTL, "typ": "refresh"}, settings.jwt_secret, "HS256"
    )
    return {"access_token": access, "refresh_token": refresh, "expires_in": ACCESS_TOKEN_TTL}


def refresh(refresh_token: str) -> dict:
    claims = jwt.decode(refresh_token, settings.jwt_secret, algorithms=["HS256"])
    if claims.get("typ") != "refresh":
        raise PermissionError("not a refresh token")
    return issue_tokens(claims["sub"])

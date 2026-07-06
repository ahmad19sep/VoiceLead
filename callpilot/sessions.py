from __future__ import annotations

import base64
from http.cookies import SimpleCookie
import hmac
import hashlib
import json
import os
from typing import Any


SESSION_COOKIE = "callpilot_session"


def _secret() -> bytes:
    return os.environ.get("SECRET_KEY", "change-me").encode("utf-8")


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode((raw + padding).encode("ascii"))


def sign_session(payload: dict[str, Any]) -> str:
    body = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def verify_session(value: str | None) -> dict[str, Any]:
    if not value or "." not in value:
        return {}
    body, signature = value.rsplit(".", 1)
    expected = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return {}
    try:
        payload = json.loads(_b64decode(body).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def session_from_cookie_header(cookie_header: str | None) -> dict[str, Any]:
    if not cookie_header:
        return {}
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except Exception:
        return {}
    morsel = cookie.get(SESSION_COOKIE)
    return verify_session(morsel.value if morsel else None)


def _served_over_https() -> bool:
    return (os.environ.get("APP_URL") or "").strip().lower().startswith("https://")


def build_session_cookie(payload: dict[str, Any], max_age: int = 60 * 60 * 24 * 30) -> str:
    cookie = SimpleCookie()
    cookie[SESSION_COOKIE] = sign_session(payload)
    cookie[SESSION_COOKIE]["path"] = "/"
    cookie[SESSION_COOKIE]["httponly"] = True
    cookie[SESSION_COOKIE]["samesite"] = "Lax"
    cookie[SESSION_COOKIE]["max-age"] = str(max_age)
    if _served_over_https():
        cookie[SESSION_COOKIE]["secure"] = True
    return cookie.output(header="").strip()

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Any

from .integrations import env_connected
from .telephony import app_url


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_production() -> bool:
    return os.environ.get("APP_ENV", "local").strip().lower() in {"prod", "production"}


def public_app_url_ready() -> bool:
    url = app_url().lower()
    return url.startswith("https://") and "127.0.0.1" not in url and "localhost" not in url


def twilio_signature_required() -> bool:
    return env_flag("TWILIO_REQUIRE_SIGNATURE", is_production())


def twilio_expected_signature(url: str, params: dict[str, str], auth_token: str) -> str:
    payload = url + "".join(f"{key}{params[key]}" for key in sorted(params))
    digest = hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def validate_twilio_signature(url: str, params: dict[str, str], signature: str | None) -> tuple[bool, str]:
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not token:
        return (not twilio_signature_required(), "TWILIO_AUTH_TOKEN is missing; signature validation is unavailable.")
    if not signature:
        return False, "Missing X-Twilio-Signature header."
    expected = twilio_expected_signature(url, params, token)
    if hmac.compare_digest(expected, signature):
        return True, "Twilio signature verified."
    return False, "Invalid Twilio signature."


def provider_statuses() -> list[dict[str, Any]]:
    public_url = public_app_url_ready()
    return [
        {
            "provider": "Twilio Voice",
            "connected": env_connected("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"),
            "production_ready": env_connected("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER")
            and public_url
            and twilio_signature_required(),
            "requirements": [
                "TWILIO_ACCOUNT_SID",
                "TWILIO_AUTH_TOKEN",
                "TWILIO_PHONE_NUMBER",
                "APP_URL public HTTPS",
                "TWILIO_REQUIRE_SIGNATURE=true in production",
            ],
        },
        {
            "provider": "OpenAI",
            "connected": env_connected("OPENAI_API_KEY"),
            "production_ready": env_connected("OPENAI_API_KEY"),
            "requirements": ["OPENAI_API_KEY", "model/runtime adapter"],
        },
        {
            "provider": "Vapi",
            "connected": env_connected("VAPI_API_KEY"),
            "production_ready": env_connected("VAPI_API_KEY"),
            "requirements": ["VAPI_API_KEY", "webhook signing policy"],
        },
        {
            "provider": "Retell",
            "connected": env_connected("RETELL_API_KEY"),
            "production_ready": env_connected("RETELL_API_KEY"),
            "requirements": ["RETELL_API_KEY", "webhook signing policy"],
        },
        {
            "provider": "Deepgram",
            "connected": env_connected("DEEPGRAM_API_KEY"),
            "production_ready": env_connected("DEEPGRAM_API_KEY"),
            "requirements": ["DEEPGRAM_API_KEY"],
        },
        {
            "provider": "ElevenLabs",
            "connected": env_connected("ELEVENLABS_API_KEY"),
            "production_ready": env_connected("ELEVENLABS_API_KEY"),
            "requirements": ["ELEVENLABS_API_KEY"],
        },
    ]


def system_readiness() -> dict[str, Any]:
    statuses = provider_statuses()
    blockers = []
    warnings = []
    if is_production() and os.environ.get("SECRET_KEY", "change-me") == "change-me":
        blockers.append("SECRET_KEY must be changed in production.")
    if is_production() and not public_app_url_ready():
        blockers.append("APP_URL must be a public HTTPS URL in production.")
    if is_production() and not twilio_signature_required():
        blockers.append("Twilio webhook signature verification must be required in production.")
    if not public_app_url_ready():
        warnings.append("APP_URL is local; real telephony providers cannot reach this server directly.")
    if not any(status["connected"] for status in statuses):
        warnings.append("No production voice/AI providers are connected; app remains in demo mode.")
    if not twilio_signature_required():
        warnings.append("Twilio signature verification is not required unless APP_ENV=production or TWILIO_REQUIRE_SIGNATURE=true.")
    return {
        "app_env": os.environ.get("APP_ENV", "local"),
        "public_app_url_ready": public_app_url_ready(),
        "twilio_signature_required": twilio_signature_required(),
        "providers": statuses,
        "blockers": blockers,
        "warnings": warnings,
        "ready_for_production": not blockers and public_app_url_ready() and any(status["production_ready"] for status in statuses),
    }

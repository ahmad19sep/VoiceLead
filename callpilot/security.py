from __future__ import annotations

import os
from typing import Any

from .config import APP_NAME
from .providers import (
    env_flag,
    is_production,
    provider_statuses,
    public_app_url_ready,
    twilio_expected_signature,
    twilio_signature_required,
    validate_twilio_signature,
)
from .storage import db
from .utils import now

__all__ = [
    "env_flag",
    "health_probe",
    "is_production",
    "provider_statuses",
    "public_app_url_ready",
    "readiness_probe",
    "system_readiness",
    "twilio_expected_signature",
    "twilio_signature_required",
    "validate_twilio_signature",
]


def health_probe() -> dict[str, Any]:
    return {
        "success": True,
        "status": "ok",
        "app": APP_NAME,
        "checked_at": now(),
    }


def database_readiness() -> dict[str, Any]:
    try:
        with db() as conn:
            business_count = int(conn.execute("select count(*) from businesses").fetchone()[0])
        return {
            "connected": True,
            "schema_ready": True,
            "business_count": business_count,
            "message": "SQLite database is reachable.",
        }
    except Exception as exc:
        return {
            "connected": False,
            "schema_ready": False,
            "business_count": 0,
            "message": str(exc),
        }


def readiness_probe() -> dict[str, Any]:
    database = database_readiness()
    system = system_readiness()
    ready = bool(database["connected"] and database["schema_ready"] and not system["blockers"])
    return {
        "success": ready,
        "status": "ready" if ready else "not_ready",
        "checked_at": now(),
        "database": database,
        "system": {
            "app_env": system["app_env"],
            "public_app_url_ready": system["public_app_url_ready"],
            "twilio_signature_required": system["twilio_signature_required"],
            "ready_for_production": system["ready_for_production"],
            "blockers": system["blockers"],
            "warnings": system["warnings"],
        },
    }


def system_readiness() -> dict[str, Any]:
    statuses = provider_statuses()
    blockers = []
    warnings = []
    if is_production() and os.environ.get("SECRET_KEY", "change-me") == "change-me":
        blockers.append("SECRET_KEY must be changed in production.")
    from .auth import auth_required

    if is_production() and not auth_required():
        blockers.append("AUTH_REQUIRED must not be disabled in production.")
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

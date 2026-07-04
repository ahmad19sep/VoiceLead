from __future__ import annotations

import os
from typing import Any

from .providers import (
    env_flag,
    is_production,
    provider_statuses,
    public_app_url_ready,
    twilio_expected_signature,
    twilio_signature_required,
    validate_twilio_signature,
)

__all__ = [
    "env_flag",
    "is_production",
    "provider_statuses",
    "public_app_url_ready",
    "system_readiness",
    "twilio_expected_signature",
    "twilio_signature_required",
    "validate_twilio_signature",
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

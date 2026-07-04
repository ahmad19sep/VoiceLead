from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from dataclasses import asdict, dataclass
from typing import Any

from .integrations import env_connected
from .telephony import app_url, create_twilio_outbound_call


@dataclass(frozen=True)
class ProviderResult:
    success: bool
    provider: str
    action: str
    message: str
    provider_call_id: str | None = None
    raw_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProviderAdapter:
    key = "provider"
    name = "Provider"
    category = "generic"
    capabilities: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()

    def connected(self) -> bool:
        return False

    def production_ready(self) -> bool:
        return False

    def health(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "provider": self.name,
            "category": self.category,
            "connected": self.connected(),
            "production_ready": self.production_ready(),
            "capabilities": list(self.capabilities),
            "requirements": list(self.requirements),
        }

    def create_outbound_call(self, to_number: str, business_id: int) -> ProviderResult:
        return ProviderResult(
            False,
            self.name,
            "create_outbound_call",
            f"{self.name} outbound calling is not implemented in this adapter.",
        )

    def verify_webhook(self, url: str, params: dict[str, str], signature: str | None) -> ProviderResult:
        return ProviderResult(False, self.name, "verify_webhook", f"{self.name} webhook verification is not implemented.")


class EnvProviderAdapter(ProviderAdapter):
    env_keys: tuple[str, ...] = ()
    ready_requires_adapter = True

    def connected(self) -> bool:
        return env_connected(*self.env_keys) if self.env_keys else False

    def production_ready(self) -> bool:
        return self.connected() and not self.ready_requires_adapter


class TwilioVoiceProvider(ProviderAdapter):
    key = "twilio"
    name = "Twilio Voice"
    category = "telephony"
    capabilities = ("inbound_voice", "outbound_voice", "speech_gather", "status_webhook", "recording_metadata")
    requirements = (
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_PHONE_NUMBER",
        "APP_URL public HTTPS",
        "TWILIO_REQUIRE_SIGNATURE=true in production",
    )

    def connected(self) -> bool:
        return env_connected("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER")

    def production_ready(self) -> bool:
        return self.connected() and public_app_url_ready() and twilio_signature_required()

    def create_outbound_call(self, to_number: str, business_id: int) -> ProviderResult:
        ok, message = create_twilio_outbound_call(to_number, business_id)
        call_sid = None
        match = re.search(r"\b(CA[a-fA-F0-9]{32})\b", message)
        if match:
            call_sid = match.group(1)
        return ProviderResult(ok, self.name, "create_outbound_call", message, call_sid, "created" if ok else "failed")

    def verify_webhook(self, url: str, params: dict[str, str], signature: str | None) -> ProviderResult:
        ok, message = validate_twilio_signature(url, params, signature)
        return ProviderResult(ok, self.name, "verify_webhook", message, raw_status="verified" if ok else "rejected")


class OpenAIProvider(EnvProviderAdapter):
    key = "openai"
    name = "OpenAI"
    category = "ai"
    env_keys = ("OPENAI_API_KEY",)
    capabilities = ("responses", "realtime_voice", "speech_to_text", "text_to_speech")
    requirements = ("OPENAI_API_KEY", "model/runtime adapter")


class VapiProvider(EnvProviderAdapter):
    key = "vapi"
    name = "Vapi"
    category = "voice_runtime"
    env_keys = ("VAPI_API_KEY",)
    capabilities = ("voice_agent_runtime", "inbound_voice", "outbound_voice", "transfer")
    requirements = ("VAPI_API_KEY", "webhook signing policy", "provider adapter")


class RetellProvider(EnvProviderAdapter):
    key = "retell"
    name = "Retell"
    category = "voice_runtime"
    env_keys = ("RETELL_API_KEY",)
    capabilities = ("voice_agent_runtime", "inbound_voice", "outbound_voice", "transfer")
    requirements = ("RETELL_API_KEY", "webhook signing policy", "provider adapter")


class DeepgramProvider(EnvProviderAdapter):
    key = "deepgram"
    name = "Deepgram"
    category = "speech"
    env_keys = ("DEEPGRAM_API_KEY",)
    capabilities = ("speech_to_text", "language_detection")
    requirements = ("DEEPGRAM_API_KEY", "speech adapter")


class ElevenLabsProvider(EnvProviderAdapter):
    key = "elevenlabs"
    name = "ElevenLabs"
    category = "speech"
    env_keys = ("ELEVENLABS_API_KEY",)
    capabilities = ("text_to_speech", "voice_library")
    requirements = ("ELEVENLABS_API_KEY", "TTS adapter")


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


def provider_registry() -> dict[str, ProviderAdapter]:
    providers: list[ProviderAdapter] = [
        TwilioVoiceProvider(),
        OpenAIProvider(),
        VapiProvider(),
        RetellProvider(),
        DeepgramProvider(),
        ElevenLabsProvider(),
    ]
    return {provider.key: provider for provider in providers}


def provider_by_key(key: str | None) -> ProviderAdapter:
    registry = provider_registry()
    return registry.get(key or "twilio", registry["twilio"])


def provider_statuses() -> list[dict[str, Any]]:
    return [provider.health() for provider in provider_registry().values()]


def create_outbound_call(provider_key: str | None, to_number: str, business_id: int) -> ProviderResult:
    return provider_by_key(provider_key).create_outbound_call(to_number, business_id)

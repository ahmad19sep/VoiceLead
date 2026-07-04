from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from callpilot.providers import (
    create_outbound_call,
    provider_by_key,
    provider_statuses,
    twilio_expected_signature,
    validate_twilio_signature,
)


class ProviderRegistryTest(unittest.TestCase):
    def test_provider_registry_exposes_required_adapters(self) -> None:
        statuses = {row["key"]: row for row in provider_statuses()}

        self.assertIn("twilio", statuses)
        self.assertIn("openai", statuses)
        self.assertIn("vapi", statuses)
        self.assertIn("retell", statuses)
        self.assertIn("deepgram", statuses)
        self.assertIn("elevenlabs", statuses)
        self.assertIn("outbound_voice", statuses["twilio"]["capabilities"])

    def test_unknown_provider_falls_back_to_twilio_adapter(self) -> None:
        provider = provider_by_key("unknown")

        self.assertEqual(provider.key, "twilio")

    def test_outbound_without_twilio_credentials_fails_honestly(self) -> None:
        env = {
            "TWILIO_ACCOUNT_SID": "",
            "TWILIO_AUTH_TOKEN": "",
            "TWILIO_PHONE_NUMBER": "",
            "APP_URL": "http://127.0.0.1:8000",
        }
        with patch.dict(os.environ, env, clear=False):
            result = create_outbound_call("twilio", "+923001234567", 1)

        self.assertFalse(result.success)
        self.assertEqual(result.provider, "Twilio Voice")
        self.assertIn("Missing TWILIO_ACCOUNT_SID", result.message)

    def test_twilio_signature_validation(self) -> None:
        url = "https://example.com/api/twilio/voice?business_id=1"
        params = {"CallSid": "CA123", "From": "+123"}
        signature = twilio_expected_signature(url, params, "secret")

        with patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": "secret"}, clear=False):
            ok, message = validate_twilio_signature(url, params, signature)

        self.assertTrue(ok)
        self.assertEqual(message, "Twilio signature verified.")


if __name__ == "__main__":
    unittest.main()

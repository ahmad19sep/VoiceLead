from __future__ import annotations

import gc
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot import ai_analysis
from callpilot.ai_analysis import analyze_call_smart, merge_ai_extraction
from callpilot.repositories import get_business, get_businesses, get_services


TRANSCRIPT = (
    "Hi, my name is Sarah Ahmed. I want to book a cleaning appointment on 2026-07-15. "
    "My number is 0301 5551234."
)


class AiAnalysisTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "callpilot-test.db"
        self.patch = patch.object(storage, "DB_PATH", self.db_path)
        self.patch.start()
        storage.init_db()
        with storage.db() as conn:
            clinic = [row for row in get_businesses(conn) if row["name"] == "BrightCare Dental Clinic"][0]
            self.business = get_business(conn, int(clinic["id"]))
            self.services = get_services(conn, int(clinic["id"]))

    def tearDown(self) -> None:
        self.patch.stop()
        gc.collect()
        self.temp_dir.cleanup()

    def test_without_key_falls_back_to_rule_based(self) -> None:
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            analysis = analyze_call_smart(TRANSCRIPT, self.business, self.services, [])
        self.assertEqual(analysis["ai_provider"], "rule_based")
        self.assertEqual(analysis["customer_name"], "Sarah Ahmed")

    def test_api_error_is_honest_and_keeps_rule_based_result(self) -> None:
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
            with patch.object(ai_analysis, "_extract_with_claude", side_effect=RuntimeError("boom 500")):
                analysis = analyze_call_smart(TRANSCRIPT, self.business, self.services, [])
        self.assertEqual(analysis["ai_provider"], "rule_based")
        self.assertIn("boom 500", analysis["ai_error"])
        self.assertTrue(analysis["booking_requested"])

    def test_claude_extraction_is_merged_when_available(self) -> None:
        extracted = {
            "customer_name": "Sarah Ahmed",
            "customer_phone": "0301 5551234",
            "customer_email": "",
            "service_requested": "Teeth cleaning",
            "requested_date": "2026-07-15",
            "requested_time": "10:30",
            "language": "en",
            "intent": "ready_to_book",
            "booking_requested": True,
            "emergency_indicated": False,
            "advice_requested": False,
            "summary": "Sarah Ahmed wants a teeth cleaning on 2026-07-15 and left a callback number.",
        }
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
            with patch.object(ai_analysis, "_extract_with_claude", return_value=extracted):
                analysis = analyze_call_smart(TRANSCRIPT, self.business, self.services, [])
        self.assertEqual(analysis["ai_provider"], ai_analysis.configured_model())
        self.assertEqual(analysis["service_requested"], "Teeth cleaning")
        self.assertEqual(analysis["extracted_fields"]["requested_time"], "10:30")
        self.assertIn("teeth cleaning", analysis["ai_summary"].lower())

    def test_hallucinated_contact_details_are_discarded(self) -> None:
        base = {
            "customer_name": None,
            "customer_phone": None,
            "customer_email": None,
            "booking_requested": False,
            "handoff_triggered": False,
            "extracted_fields": {},
        }
        extracted = {
            "customer_name": "Invented Person",
            "customer_phone": "0399 0000000",
            "customer_email": "ghost@example.com",
            "booking_requested": False,
            "emergency_indicated": False,
            "advice_requested": False,
        }
        merged = merge_ai_extraction(base, extracted, "Hello, I just want your opening hours.")
        self.assertIsNone(merged["customer_name"])
        self.assertIsNone(merged["customer_phone"])
        self.assertIsNone(merged["customer_email"])

    def test_safety_flags_only_ratchet_up_never_down(self) -> None:
        base = {
            "booking_requested": True,
            "handoff_triggered": True,
            "urgency": "emergency",
            "extracted_fields": {"medical_emergency": {"detected": True, "language": "ur", "match_type": "exact"}},
        }
        extracted = {
            "customer_name": "",
            "customer_phone": "",
            "customer_email": "",
            "booking_requested": False,
            "emergency_indicated": False,  # Claude disagrees - must NOT clear the rule-based flag
            "advice_requested": False,
        }
        merged = merge_ai_extraction(base, extracted, "saans nahi aa rahi")
        self.assertTrue(merged["extracted_fields"]["medical_emergency"]["detected"])
        self.assertTrue(merged["handoff_triggered"])
        self.assertTrue(merged["booking_requested"])

        # And the reverse: Claude CAN add an emergency the rules missed.
        base2 = {"booking_requested": False, "handoff_triggered": False, "extracted_fields": {}}
        extracted2 = dict(extracted, emergency_indicated=True)
        merged2 = merge_ai_extraction(base2, extracted2, "some subtle emergency phrasing")
        self.assertTrue(merged2["extracted_fields"]["medical_emergency"]["detected"])
        self.assertEqual(merged2["extracted_fields"]["medical_emergency"]["match_type"], "ai")
        self.assertTrue(merged2["handoff_triggered"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.golden import load_golden_scripts, run_golden_suite


class GoldenCallHarnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "callpilot-test.db"
        self.patch = patch.object(storage, "DB_PATH", self.db_path)
        self.patch.start()
        storage.init_db()

    def tearDown(self) -> None:
        self.patch.stop()
        gc.collect()
        self.temp_dir.cleanup()

    def test_suite_covers_three_languages_and_emergencies(self) -> None:
        scripts = load_golden_scripts()
        self.assertGreaterEqual(len(scripts), 10)
        languages = {script.get("language") for script in scripts}
        self.assertEqual(languages, {"en", "ur", "ar"})
        emergencies = [s for s in scripts if s.get("expect", {}).get("medical_emergency") is True]
        self.assertGreaterEqual(len(emergencies), 3)

    def test_every_golden_script_passes(self) -> None:
        with storage.db() as conn:
            report = run_golden_suite(conn)
        failures = []
        for result in report["results"]:
            for item in result["failed_checks"]:
                failures.append(f"{result['name']}: {item['check']} -> {item['details']}")
        self.assertEqual(failures, [], "Golden call regressions:\n" + "\n".join(failures))
        self.assertEqual(report["failed"], 0)
        self.assertEqual(report["languages"], ["ar", "en", "ur"])

    def test_hallucination_guards_catch_invented_contact(self) -> None:
        from callpilot.golden import hallucination_checks

        transcript = "Hello, I want to know your prices."
        fake_analysis = {
            "customer_phone": "0300 9998877",
            "customer_email": "made-up@example.com",
            "customer_name": "Invented Person",
            "ai_summary": "Caller asked about prices. Contact details were provided.",
            "lead_score": 40,
        }
        results: list[dict] = []
        hallucination_checks(transcript, fake_analysis, results)
        failed = {item["check"] for item in results if not item["passed"]}
        self.assertIn("no_invented_phone", failed)
        self.assertIn("no_invented_email", failed)
        self.assertIn("no_invented_name", failed)

        # Separate case: summary claims contact details although none were captured.
        ungrounded = {
            "customer_phone": None,
            "customer_email": None,
            "customer_name": None,
            "ai_summary": "Caller asked about prices. Contact details were provided.",
            "lead_score": 40,
        }
        results2: list[dict] = []
        hallucination_checks(transcript, ungrounded, results2)
        failed2 = {item["check"] for item in results2 if not item["passed"]}
        self.assertIn("summary_contact_claim_grounded", failed2)


class DateExtractionRegressionTest(unittest.TestCase):
    def test_explicit_dates_and_24h_times_are_extracted(self) -> None:
        from callpilot.analysis import extract_time, extract_timeline

        transcript = "I want to book a cleaning appointment on 2026-07-08 at 11:00 please."
        self.assertEqual(extract_timeline(transcript), "2026-07-08")
        self.assertEqual(extract_time(transcript), "11:00")
        self.assertEqual(extract_timeline("book me for 08/07/2026"), "08/07/2026")
        self.assertEqual(extract_time("come at 3:30 pm"), "3:30 pm")
        self.assertEqual(extract_timeline("I need it tomorrow"), "tomorrow")
        self.assertIsNone(extract_time("the year 2026-07-08 alone is not a time"))

    def test_urdu_and_arabic_time_date_phrases(self) -> None:
        from callpilot.analysis import extract_time, extract_timeline, normalize_digits

        self.assertEqual(extract_time("kal subah 11 baje aana hai"), "11:00")
        self.assertEqual(extract_time("shaam 5 baje ka time"), "17:00")
        self.assertEqual(extract_time("الساعة ٤ مساء"), "16:00")
        self.assertEqual(extract_timeline("mujhe kal appointment chahiye"), "kal")
        self.assertEqual(extract_timeline("parso ka waqt mil jaye"), "parso")
        self.assertEqual(extract_timeline("agla mangal ko"), "agla mangal")
        self.assertIsNotNone(extract_timeline("أريد موعدا غدا"))
        self.assertEqual(normalize_digits("٠٣٠٠١٢٣٤٥٦٧"), "03001234567")


if __name__ == "__main__":
    unittest.main()

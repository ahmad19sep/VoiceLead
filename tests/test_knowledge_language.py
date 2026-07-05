from __future__ import annotations

import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.knowledge import ingest_knowledge_document, search_knowledge
from callpilot.repositories import get_businesses


class KnowledgeLanguageTest(unittest.TestCase):
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

    def clinic_id(self) -> int:
        with storage.db() as conn:
            clinic = [row for row in get_businesses(conn) if row["name"] == "BrightCare Dental Clinic"][0]
            return int(clinic["id"])

    def test_search_prefers_requested_knowledge_language(self) -> None:
        business_id = self.clinic_id()
        with storage.db() as conn:
            result = ingest_knowledge_document(
                conn,
                business_id,
                "Trilingual hours",
                "manual",
                "operator",
                "\n".join(
                    [
                        "What are clinic timings? | We are open from 9 AM to 6 PM. | Hours | timings | en | hours",
                        "Clinic timings kya hain? | Clinic subah 9 se shaam 6 tak open hai. | Hours | timings | ur | hours",
                        "ما هي مواعيد العيادة؟ | العيادة مفتوحة من 9 صباحا إلى 6 مساء. | Hours | timings | ar | hours",
                    ]
                ),
            )
            ur_results = search_knowledge(conn, business_id, "timings", "ur")
            ar_results = search_knowledge(conn, business_id, "timings", "ar")

        self.assertTrue(result["success"])
        self.assertEqual(ur_results[0]["answer_language"], "ur")
        self.assertFalse(ur_results[0]["translated"])
        self.assertIn("subah", ur_results[0]["answer"])
        self.assertEqual(ar_results[0]["answer_language"], "ar")

    def test_search_falls_back_to_english_with_translation_flag(self) -> None:
        business_id = self.clinic_id()
        with storage.db() as conn:
            ingest_knowledge_document(
                conn,
                business_id,
                "Insurance policy",
                "manual",
                "operator",
                "Do you accept Jubilee insurance? | Jubilee panel is accepted after staff verification. | Insurance | insurance | en | insurance",
            )
            results = search_knowledge(conn, business_id, "insurance", "ur")

        self.assertEqual(results[0]["answer_language"], "en")
        self.assertTrue(results[0]["translated"])
        self.assertEqual(results[0]["requested_language"], "ur")

    def test_unapproved_language_items_are_not_returned(self) -> None:
        business_id = self.clinic_id()
        with storage.db() as conn:
            conn.execute(
                """
                insert into knowledge_base (
                    business_id, question, answer, category, tags, source, language,
                    translation_group_id, status
                )
                values (?, 'Draft Arabic answer?', 'Draft answer', 'FAQ', 'draft', 'test', 'ar', 'draft', 'draft')
                """,
                (business_id,),
            )
            results = search_knowledge(conn, business_id, "draft", "ar")

        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()

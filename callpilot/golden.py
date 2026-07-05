from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .analysis import analyze_call
from .repositories import get_business, get_businesses, get_knowledge, get_services
from .voice_runtime import build_runtime_session, detect_language_code


GOLDEN_HARNESS_VERSION = "clinic-golden-v1"
GOLDEN_DIR = Path(__file__).resolve().parent.parent / "tests" / "golden_calls"

# Phrases that must never appear in AI summaries or recommended actions for a
# clinic: they would mean the assistant gave medical advice.
FORBIDDEN_ADVICE_PATTERNS = (
    r"\byou should take\b",
    r"\bprescrib",
    r"\bdiagnos(?:is|ed) is\b",
    r"\btake (?:this |these )?(?:medicine|medication|antibiotic)",
    r"\bincrease the dose\b",
)


def load_golden_scripts(directory: Path | None = None) -> list[dict[str, Any]]:
    folder = directory or GOLDEN_DIR
    scripts = []
    for path in sorted(folder.glob("*.json")):
        with open(path, encoding="utf-8") as handle:
            script = json.load(handle)
        script["_file"] = path.name
        scripts.append(script)
    return scripts


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _check(results: list[dict[str, Any]], name: str, passed: bool, details: str = "") -> None:
    results.append({"check": name, "passed": bool(passed), "details": details})


def hallucination_checks(transcript: str, analysis: dict[str, Any], results: list[dict[str, Any]]) -> None:
    """Everything the analysis asserts about the caller must be grounded in the transcript."""
    transcript_digits = _digits(transcript)
    phone = analysis.get("customer_phone") or ""
    if phone:
        _check(
            results,
            "no_invented_phone",
            _digits(phone) in transcript_digits,
            f"analysis phone {phone!r} not present in transcript",
        )
    else:
        _check(results, "no_invented_phone", True)
    email = analysis.get("customer_email") or ""
    _check(
        results,
        "no_invented_email",
        (not email) or (email.lower() in transcript.lower()),
        f"analysis email {email!r} not present in transcript",
    )
    name = analysis.get("customer_name") or ""
    _check(
        results,
        "no_invented_name",
        (not name) or (name.lower() in transcript.lower()),
        f"analysis name {name!r} not present in transcript",
    )
    summary = analysis.get("ai_summary") or ""
    claims_contact = "contact details were provided" in summary.lower()
    has_contact = bool(phone or email)
    _check(
        results,
        "summary_contact_claim_grounded",
        (not claims_contact) or has_contact,
        "summary claims contact details that were never captured",
    )
    score = analysis.get("lead_score")
    _check(results, "score_in_range", isinstance(score, int) and 0 <= score <= 100, f"score={score!r}")


def safety_checks(analysis: dict[str, Any], results: list[dict[str, Any]]) -> None:
    text = " ".join(
        [
            analysis.get("ai_summary") or "",
            analysis.get("recommended_action") or "",
        ]
    ).lower()
    violations = [pattern for pattern in FORBIDDEN_ADVICE_PATTERNS if re.search(pattern, text)]
    _check(
        results,
        "no_medical_advice_in_output",
        not violations,
        f"forbidden advice patterns matched: {violations}",
    )


def run_golden_script(conn: sqlite3.Connection, business: dict[str, Any], script: dict[str, Any]) -> dict[str, Any]:
    transcript = script["transcript"]
    expect = script.get("expect", {})
    results: list[dict[str, Any]] = []

    analysis = analyze_call(
        transcript, business, get_services(conn, int(business["id"])), get_knowledge(conn, int(business["id"]))
    )
    fields = analysis.get("extracted_fields") or {}

    if "language_code" in expect:
        detected = detect_language_code(transcript)
        _check(
            results,
            "language_code",
            detected == expect["language_code"],
            f"expected {expect['language_code']} got {detected}",
        )
    if "booking_requested" in expect:
        _check(
            results,
            "booking_requested",
            bool(analysis.get("booking_requested")) == bool(expect["booking_requested"]),
            f"expected {expect['booking_requested']} got {analysis.get('booking_requested')}",
        )
    if "medical_emergency" in expect:
        detected_emergency = bool((fields.get("medical_emergency") or {}).get("detected"))
        _check(
            results,
            "medical_emergency",
            detected_emergency == bool(expect["medical_emergency"]),
            f"expected {expect['medical_emergency']} got {detected_emergency}",
        )
    if "handoff_triggered" in expect:
        _check(
            results,
            "handoff_triggered",
            bool(analysis.get("handoff_triggered")) == bool(expect["handoff_triggered"]),
            f"expected {expect['handoff_triggered']} got {analysis.get('handoff_triggered')}",
        )
    if "urgency" in expect:
        _check(
            results,
            "urgency",
            (analysis.get("urgency") or None) == expect["urgency"],
            f"expected {expect['urgency']} got {analysis.get('urgency')}",
        )
    if "session_language" in expect:
        session = build_runtime_session(conn, int(business["id"]), caller_text=transcript)
        _check(
            results,
            "session_language",
            session["language"] == expect["session_language"],
            f"expected {expect['session_language']} got {session['language']}",
        )
    for phrase in expect.get("summary_must_not_contain", []):
        _check(
            results,
            f"summary_excludes:{phrase}",
            phrase.lower() not in (analysis.get("ai_summary") or "").lower(),
            "forbidden phrase found in summary",
        )

    hallucination_checks(transcript, analysis, results)
    safety_checks(analysis, results)

    failed = [item for item in results if not item["passed"]]
    return {
        "name": script.get("name") or script["_file"],
        "file": script["_file"],
        "language": script.get("language"),
        "passed": not failed,
        "checks": results,
        "failed_checks": failed,
    }


def run_golden_suite(conn: sqlite3.Connection, directory: Path | None = None) -> dict[str, Any]:
    scripts = load_golden_scripts(directory)
    clinics = [row for row in get_businesses(conn) if row["business_type"] in {"Clinic", "Hospital", "Dentist"}]
    if not clinics:
        raise RuntimeError("No clinic business found for the golden harness.")
    business = get_business(conn, int(clinics[0]["id"]))
    results = [run_golden_script(conn, business, script) for script in scripts]
    failed = [result for result in results if not result["passed"]]
    languages = sorted({result["language"] for result in results if result["language"]})
    return {
        "version": GOLDEN_HARNESS_VERSION,
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "languages": languages,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    import gc
    import os
    import tempfile

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        os.environ["SQLITE_DB_PATH"] = str(Path(tmp) / "golden.db")
        from .storage import db, init_db

        init_db()
        conn = db()
        try:
            report = run_golden_suite(conn)
        finally:
            conn.close()
            gc.collect()
    print(f"Golden call harness {report['version']}: "
          f"{report['passed']}/{report['total']} scripts passed across languages {report['languages']}.")
    for result in report["results"]:
        marker = "PASS" if result["passed"] else "FAIL"
        print(f"  [{marker}] {result['name']} ({result['language']})")
        for item in result["failed_checks"]:
            print(f"         - {item['check']}: {item['details']}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

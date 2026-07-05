from __future__ import annotations

import argparse
import os
import time
from typing import Any

from .config import APP_NAME, load_dotenv
from .jobs import run_due_jobs
from .storage import db, init_db


def env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


def run_worker_once(limit: int | None = None) -> list[dict[str, Any]]:
    from .reminders import schedule_appointment_reminders

    with db() as conn:
        schedule_appointment_reminders(conn)
        return run_due_jobs(conn, limit=limit or env_int("WORKER_BATCH_LIMIT", 20))


def worker_loop(interval_seconds: int | None = None, limit: int | None = None) -> None:
    interval_seconds = interval_seconds or env_int("WORKER_POLL_INTERVAL", 10)
    limit = limit or env_int("WORKER_BATCH_LIMIT", 20)
    print(f"{APP_NAME} worker running every {interval_seconds}s with batch limit {limit}.")
    print("Press Ctrl+C to stop.")
    while True:
        results = run_worker_once(limit)
        if results:
            print(f"Processed {len(results)} job(s): {results}")
        time.sleep(interval_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the CallPilot background job worker.")
    parser.add_argument("--once", action="store_true", help="Run due jobs once and exit.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum jobs to process per batch.")
    parser.add_argument("--interval", type=int, default=None, help="Polling interval in seconds.")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    init_db()
    args = build_parser().parse_args(argv)
    limit = args.limit if args.limit and args.limit > 0 else None
    if args.once:
        results = run_worker_once(limit)
        print(f"Processed {len(results)} job(s).")
        return 0
    try:
        worker_loop(args.interval if args.interval and args.interval > 0 else None, limit)
    except KeyboardInterrupt:
        print("\nWorker stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

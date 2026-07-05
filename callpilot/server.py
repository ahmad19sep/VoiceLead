from __future__ import annotations

import os
import threading
import time
from http.server import ThreadingHTTPServer

from .config import APP_NAME, load_dotenv
from .http import CallPilotHandler
from .storage import init_db


def inline_worker_enabled() -> bool:
    value = (os.environ.get("INLINE_WORKER") or "true").strip().lower()
    return value in {"1", "true", "yes", "on"}


def inline_worker_interval(default: int = 300) -> int:
    raw = (os.environ.get("WORKER_POLL_INTERVAL") or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 30 else default


def start_inline_worker() -> threading.Thread | None:
    """Run due jobs inside the web process on single-service deploys.

    Free-tier hosts run only `python app.py`; without this, scheduled work
    (appointment reminders, campaign preparation) would never execute.
    Disable with INLINE_WORKER=false when a dedicated worker runs.
    """
    if not inline_worker_enabled():
        return None
    interval = inline_worker_interval()

    def loop() -> None:
        from .jobs import run_due_jobs
        from .reminders import schedule_appointment_reminders
        from .storage import db

        while True:
            time.sleep(interval)
            try:
                with db() as conn:
                    schedule_appointment_reminders(conn)
                    results = run_due_jobs(conn, limit=20)
                if results:
                    print(f"Inline worker processed {len(results)} job(s).")
            except Exception as error:  # never let the worker kill the web process
                print(f"Inline worker error: {error}")

    thread = threading.Thread(target=loop, name="callpilot-inline-worker", daemon=True)
    thread.start()
    print(f"Inline worker running every {interval}s (set INLINE_WORKER=false to disable).")
    return thread


def configured_host(default: str = "127.0.0.1") -> str:
    return os.environ.get("APP_HOST", default).strip() or default


def configured_port(default: int = 8000) -> int:
    # APP_PORT wins; PORT is the convention free hosts (Render, Railway) inject.
    raw = (os.environ.get("APP_PORT") or os.environ.get("PORT") or "").strip()
    if not raw:
        return default
    try:
        port = int(raw)
    except ValueError:
        return default
    return port if 1 <= port <= 65535 else default


def run(host: str | None = None, port: int | None = None) -> None:
    load_dotenv()
    host = host or configured_host()
    port = port or configured_port()
    init_db()
    from .auth import auth_required, ensure_demo_viewer, ensure_owner_credentials
    from .storage import db

    with db() as conn:
        one_time_password = ensure_owner_credentials(conn)
        ensure_demo_viewer(conn)
    if one_time_password:
        print("AUTH: one-time owner password generated (change it after first login):")
        print(f"AUTH: {one_time_password}")
    if auth_required():
        print("AUTH: login is required (AUTH_REQUIRED or production mode).")
    start_inline_worker()
    server = ThreadingHTTPServer((host, port), CallPilotHandler)
    print(f"{APP_NAME} running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()

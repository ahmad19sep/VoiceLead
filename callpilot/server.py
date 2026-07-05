from __future__ import annotations

import os
from http.server import ThreadingHTTPServer

from .config import APP_NAME, load_dotenv
from .http import CallPilotHandler
from .storage import init_db


def configured_host(default: str = "127.0.0.1") -> str:
    return os.environ.get("APP_HOST", default).strip() or default


def configured_port(default: int = 8000) -> int:
    raw = os.environ.get("APP_PORT", "").strip()
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
    from .auth import auth_required, ensure_owner_credentials
    from .storage import db

    with db() as conn:
        one_time_password = ensure_owner_credentials(conn)
    if one_time_password:
        print("AUTH: one-time owner password generated (change it after first login):")
        print(f"AUTH: {one_time_password}")
    if auth_required():
        print("AUTH: login is required (AUTH_REQUIRED or production mode).")
    server = ThreadingHTTPServer((host, port), CallPilotHandler)
    print(f"{APP_NAME} running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()

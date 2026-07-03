from __future__ import annotations

from http.server import ThreadingHTTPServer

from .config import APP_NAME, load_dotenv
from .http import CallPilotHandler
from .storage import init_db


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    load_dotenv()
    init_db()
    server = ThreadingHTTPServer((host, port), CallPilotHandler)
    print(f"{APP_NAME} running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()

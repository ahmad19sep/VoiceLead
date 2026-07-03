from __future__ import annotations

import os


def env_connected(*keys: str) -> bool:
    return all(bool(os.environ.get(key)) for key in keys)

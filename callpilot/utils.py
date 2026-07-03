from __future__ import annotations

import html
import json
from datetime import datetime, timedelta
from typing import Any


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def days_ago(days: int, hours: int = 0) -> str:
    return (datetime.now() - timedelta(days=days, hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)

def title(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(part.capitalize() for part in value.replace("_", " ").split())

def money_or_text(value: str | None) -> str:
    return value if value else "Not provided"

def format_dt(value: str | None) -> str:
    if not value:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt).strftime("%b %d, %I:%M %p")
        except ValueError:
            pass
    return value

def as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True)

def from_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback

def lead_temperature(score: int) -> str:
    if score >= 75:
        return "hot"
    if score >= 45:
        return "warm"
    return "cold"

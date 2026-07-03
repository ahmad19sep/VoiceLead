from __future__ import annotations

from .layout import layout


def render_not_found() -> str:
    return layout("Not Found", "", "<section class='panel pad'><h1>Page not found</h1><p><a class='btn primary' href='/'>Go to Dashboard</a></p></section>")

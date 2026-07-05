from __future__ import annotations

from ..config import APP_NAME, app_tagline
from ..utils import esc


def render_login(error: str | None = None, email: str = "") -> str:
    error_html = f'<p class="error">{esc(error)}</p>' if error else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sign in - {APP_NAME}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ margin:0; font-family: 'Segoe UI', system-ui, sans-serif; background:#f2f5f9; display:flex; align-items:center; justify-content:center; min-height:100vh; }}
    .card {{ background:#fff; border:1px solid #dbe4ee; border-radius:14px; padding:34px 36px; width:340px; box-shadow:0 12px 30px rgba(20,40,80,.08); }}
    .brand {{ display:flex; align-items:center; gap:10px; margin-bottom:6px; }}
    .mark {{ width:38px; height:38px; border-radius:10px; background:#0e5fd8; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:700; }}
    h1 {{ font-size:1.15rem; margin:0; }}
    p.tagline {{ color:#5b6b80; font-size:.85rem; margin:2px 0 18px; }}
    label {{ display:block; font-size:.8rem; font-weight:600; color:#33445c; margin:12px 0 4px; }}
    input {{ width:100%; box-sizing:border-box; padding:10px 12px; border:1px solid #c6d3e2; border-radius:8px; font-size:.9rem; }}
    button {{ width:100%; margin-top:18px; padding:11px; border:0; border-radius:8px; background:#0e5fd8; color:#fff; font-weight:600; font-size:.95rem; cursor:pointer; }}
    .error {{ background:#fdecee; border:1px solid #f5c2c7; color:#b02a37; border-radius:8px; padding:9px 12px; font-size:.82rem; }}
  </style>
</head>
<body>
  <main class="card">
    <div class="brand"><div class="mark">CP</div><h1>{APP_NAME}</h1></div>
    <p class="tagline">{esc(app_tagline())}</p>
    {error_html}
    <form method="post" action="/login">
      <label for="email">Email</label>
      <input id="email" name="email" type="email" value="{esc(email)}" required autofocus>
      <label for="password">Password</label>
      <input id="password" name="password" type="password" required>
      <button type="submit">Sign in</button>
    </form>
  </main>
</body>
</html>"""

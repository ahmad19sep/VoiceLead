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
    :root {{
      color-scheme: light dark;
      --bg:#f2f5f9; --card:#ffffff; --line:#dbe4ee; --ink:#17222c; --muted:#5b6b80;
      --label:#33445c; --input-bg:#ffffff; --primary:#0e5fd8;
      --err-bg:#fdecee; --err-line:#f5c2c7; --err-ink:#b02a37;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg:#0e1411; --card:#151d18; --line:#24312a; --ink:#e9f0eb; --muted:#8da096;
        --label:#cbd6cf; --input-bg:#101713; --primary:#2f7fe0;
        --err-bg:#3a1e26; --err-line:#5c2e3a; --err-ink:#f08398;
      }}
    }}
    body {{ margin:0; font-family: 'Segoe UI', system-ui, sans-serif; background:var(--bg); color:var(--ink); display:flex; align-items:center; justify-content:center; min-height:100vh; }}
    .card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:34px 36px; width:340px; box-shadow:0 12px 30px rgba(20,40,80,.12); }}
    .brand {{ display:flex; align-items:center; gap:10px; margin-bottom:6px; }}
    .mark {{ width:38px; height:38px; border-radius:10px; background:var(--primary); color:#fff; display:flex; align-items:center; justify-content:center; font-weight:700; }}
    h1 {{ font-size:1.15rem; margin:0; }}
    p.tagline {{ color:var(--muted); font-size:.85rem; margin:2px 0 18px; }}
    label {{ display:block; font-size:.8rem; font-weight:600; color:var(--label); margin:12px 0 4px; }}
    input {{ width:100%; box-sizing:border-box; padding:10px 12px; border:1px solid var(--line); border-radius:8px; font-size:.9rem; background:var(--input-bg); color:var(--ink); }}
    button {{ width:100%; margin-top:18px; padding:11px; border:0; border-radius:8px; background:var(--primary); color:#fff; font-weight:600; font-size:.95rem; cursor:pointer; }}
    .error {{ background:var(--err-bg); border:1px solid var(--err-line); color:var(--err-ink); border-radius:8px; padding:9px 12px; font-size:.82rem; }}
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

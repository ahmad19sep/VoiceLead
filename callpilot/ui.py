from __future__ import annotations

from typing import Any

from .config import APP_NAME, APP_TAGLINE
from .utils import esc, title


def badge(text: str, kind: str) -> str:
    return f'<span class="badge {esc(kind)}">{esc(text)}</span>'

def temp_badge(temp: str) -> str:
    return badge(title(temp), f"temp-{temp}")

def status_badge(status: str) -> str:
    return badge(title(status), f"status-{status}")

def integration_badge(connected: bool, label: str | None = None) -> str:
    if connected:
        return badge(label or "Connected", "status-active")
    return badge(label or "Missing", "status-missing")

def layout(title_text: str, active: str, content: str) -> str:
    nav = [
        ("/", "Dashboard"),
        ("/businesses", "Businesses"),
        ("/agent-builder", "Agent Builder"),
        ("/demo-call", "Demo Call"),
        ("/real-calling", "Real Calling"),
        ("/leads", "Leads"),
        ("/bookings", "Bookings"),
        ("/calls", "Calls"),
        ("/notifications", "Notifications"),
        ("/compliance", "Compliance"),
        ("/admin", "Admin"),
        ("/settings", "Settings"),
    ]
    nav_html = "".join(
        f'<a class="{"active" if active == label else ""}" href="{href}">{label}</a>' for href, label in nav
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title_text)} - {APP_NAME}</title>
  <style>
    :root {{
      --bg: #07111f;
      --panel: rgba(255,255,255,.085);
      --panel-strong: rgba(255,255,255,.13);
      --white: #f8fafc;
      --muted: #a7b5c8;
      --line: rgba(255,255,255,.16);
      --hot: #fb7185;
      --warm: #fbbf24;
      --cold: #94a3b8;
      --green: #34d399;
      --blue: #38bdf8;
      --purple: #a78bfa;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at top left, rgba(56,189,248,.22), transparent 34%),
        radial-gradient(circle at 90% 10%, rgba(167,139,250,.22), transparent 30%),
        linear-gradient(135deg, #07111f 0%, #0f172a 48%, #111827 100%);
      color: var(--white);
      font-family: Inter, Segoe UI, Arial, sans-serif;
      min-height: 100vh;
    }}
    a {{ color: inherit; text-decoration: none; }}
    .shell {{ display: grid; grid-template-columns: 274px 1fr; min-height: 100vh; }}
    .sidebar {{
      border-right: 1px solid var(--line);
      background: rgba(2,6,23,.74);
      backdrop-filter: blur(18px);
      padding: 22px 16px;
      position: sticky;
      top: 0;
      height: 100vh;
    }}
    .brand {{ display: flex; gap: 12px; align-items: center; margin-bottom: 24px; }}
    .mark {{ width: 44px; height: 44px; display: grid; place-items: center; border-radius: 12px; background: linear-gradient(135deg, var(--blue), var(--purple)); font-weight: 900; }}
    .brand strong {{ display: block; font-size: 16px; }}
    .brand span {{ color: var(--muted); font-size: 12px; }}
    .nav {{ display: grid; gap: 6px; }}
    .nav a {{ padding: 11px 12px; border-radius: 10px; color: var(--muted); font-size: 14px; font-weight: 750; }}
    .nav a:hover, .nav a.active {{ background: var(--panel-strong); color: white; }}
    .main {{ min-width: 0; }}
    .topbar {{ min-height: 70px; display: flex; justify-content: space-between; align-items: center; padding: 16px 28px; border-bottom: 1px solid var(--line); background: rgba(15,23,42,.5); backdrop-filter: blur(14px); }}
    .topbar p {{ margin: 3px 0 0; color: var(--muted); font-size: 13px; }}
    main {{ max-width: 1320px; margin: 0 auto; padding: 28px; }}
    h1 {{ margin: 0; font-size: 31px; letter-spacing: 0; }}
    h2 {{ margin: 0; font-size: 18px; }}
    h3 {{ margin: 0; font-size: 15px; }}
    p {{ line-height: 1.65; }}
    .muted {{ color: var(--muted); }}
    .hero {{ padding: 28px; border: 1px solid var(--line); border-radius: 22px; background: linear-gradient(135deg, rgba(56,189,248,.16), rgba(167,139,250,.12)); box-shadow: 0 24px 80px rgba(0,0,0,.22); }}
    .hero p {{ max-width: 880px; color: #d5deea; }}
    .grid {{ display: grid; gap: 16px; }}
    .metrics {{ grid-template-columns: repeat(6, minmax(0,1fr)); margin-top: 18px; }}
    .two {{ grid-template-columns: 1.15fr .85fr; }}
    .three {{ grid-template-columns: repeat(3, minmax(0,1fr)); }}
    .four {{ grid-template-columns: repeat(4, minmax(0,1fr)); }}
    .cards {{ grid-template-columns: repeat(3, minmax(0,1fr)); }}
    .panel {{ border: 1px solid var(--line); border-radius: 18px; background: var(--panel); box-shadow: 0 20px 70px rgba(0,0,0,.18); backdrop-filter: blur(16px); }}
    .pad {{ padding: 20px; }}
    .metric {{ padding: 18px; border: 1px solid var(--line); border-radius: 18px; background: rgba(255,255,255,.08); }}
    .metric span {{ display:block; color: var(--muted); font-size: 13px; font-weight: 750; }}
    .metric strong {{ display:block; margin-top: 9px; font-size: 30px; }}
    .hot strong {{ color: var(--hot); }} .warm strong {{ color: var(--warm); }} .cold strong {{ color: var(--cold); }} .good strong {{ color: var(--green); }}
    .row {{ display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap; }}
    .actions {{ display: flex; gap: 9px; flex-wrap: wrap; align-items: center; }}
    .btn {{ border: 1px solid var(--line); border-radius: 10px; background: rgba(255,255,255,.08); color: white; padding: 10px 14px; min-height: 40px; font-weight: 800; cursor: pointer; display: inline-flex; align-items:center; justify-content:center; }}
    .btn:hover {{ background: rgba(255,255,255,.14); }}
    .btn.primary {{ background: linear-gradient(135deg, var(--blue), var(--purple)); border-color: transparent; color: #03111f; }}
    .btn.danger {{ color: var(--hot); }}
    .badge {{ display:inline-flex; min-height:24px; align-items:center; border-radius:999px; padding:3px 9px; font-size:12px; font-weight:850; border:1px solid transparent; }}
    .temp-hot {{ background: rgba(251,113,133,.16); color: #fecdd3; border-color: rgba(251,113,133,.36); }}
    .temp-warm {{ background: rgba(251,191,36,.15); color: #fde68a; border-color: rgba(251,191,36,.36); }}
    .temp-cold {{ background: rgba(148,163,184,.16); color: #cbd5e1; border-color: rgba(148,163,184,.36); }}
    .status-active, .status-won, .status-sent, .status-connected {{ background: rgba(52,211,153,.15); color:#bbf7d0; border-color: rgba(52,211,153,.35); }}
    .status-new, .status-demo, .status-requested {{ background: rgba(56,189,248,.15); color:#bae6fd; border-color: rgba(56,189,248,.35); }}
    .status-follow_up, .status-contacted {{ background: rgba(251,191,36,.15); color:#fde68a; border-color: rgba(251,191,36,.35); }}
    .status-lost, .status-missing {{ background: rgba(251,113,133,.15); color:#fecdd3; border-color: rgba(251,113,133,.35); }}
    .list .item {{ display:block; padding: 15px 20px; border-top: 1px solid var(--line); }}
    .list .item:first-child {{ border-top: 0; }}
    .list .item:hover {{ background: rgba(255,255,255,.06); }}
    .mini {{ border:1px solid var(--line); border-radius: 14px; padding: 14px; background: rgba(255,255,255,.07); }}
    .mini span {{ color: var(--muted); font-size: 12px; font-weight: 800; display:block; }}
    .mini strong {{ display:block; margin-top:5px; }}
    table {{ width:100%; border-collapse:collapse; min-width: 940px; }}
    th {{ text-align:left; color: var(--muted); font-size:12px; text-transform:uppercase; padding:13px 16px; background:rgba(255,255,255,.06); }}
    td {{ padding:15px 16px; border-top:1px solid var(--line); vertical-align:middle; }}
    tr:hover td {{ background: rgba(255,255,255,.045); }}
    .table-wrap {{ overflow-x:auto; }}
    input, textarea, select {{ width:100%; border:1px solid var(--line); border-radius:11px; padding:11px 12px; background:rgba(2,6,23,.46); color:white; font:inherit; }}
    input[type="checkbox"] {{ width:auto; }}
    .checkline {{ display:flex; grid-template-columns:none; align-items:center; gap:10px; font-weight:800; }}
    option {{ color:#111827; }}
    textarea {{ min-height: 150px; resize:vertical; line-height:1.55; }}
    label {{ display:grid; gap:7px; font-size:14px; font-weight:800; }}
    .form-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:15px; }}
    .full {{ grid-column: 1 / -1; }}
    pre {{ white-space:pre-wrap; overflow:auto; background:rgba(2,6,23,.65); color:#e5edf8; border-radius:14px; padding:16px; line-height:1.6; }}
    .bar {{ height:9px; border-radius:999px; overflow:hidden; background:rgba(255,255,255,.11); }}
    .bar span {{ display:block; height:100%; background:linear-gradient(90deg, var(--blue), var(--purple)); }}
    @media (max-width: 1100px) {{
      .shell {{ grid-template-columns:1fr; }}
      .sidebar {{ height:auto; position:static; }}
      .nav {{ grid-template-columns: repeat(12, max-content); overflow-x:auto; }}
      .metrics, .two, .three, .four, .cards, .form-grid {{ grid-template-columns:1fr; }}
      main, .topbar {{ padding-left:16px; padding-right:16px; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand"><div class="mark">CP</div><div><strong>{APP_NAME}</strong><span>{APP_TAGLINE}</span></div></div>
      <nav class="nav">{nav_html}</nav>
    </aside>
    <div class="main">
      <header class="topbar">
        <div><strong>{APP_NAME}</strong><p>{APP_TAGLINE}</p></div>
        <div>{badge('Demo mode', 'status-demo')}</div>
      </header>
      <main>{content}</main>
    </div>
  </div>
</body>
</html>"""

def metric(label: str, value: Any, kind: str = "") -> str:
    return f'<div class="metric {esc(kind)}"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>'

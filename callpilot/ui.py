from __future__ import annotations

import base64
import hashlib
from typing import Any

from .config import APP_NAME, app_tagline, clinic_mode
from .compliance import role_allows, workspace_context
from .storage import db
from .utils import esc, title


LIGHT_VARS = """--bg: #f5f7f8;
      --panel: #ffffff;
      --panel-soft: #f8faf9;
      --sidebar-bg: #fbfcfb;
      --topbar-bg: rgba(255,255,255,.78);
      --nav-hover: #f1f5f3;
      --input-bg: #ffffff;
      --track: #edf1ef;
      --ink: #17201b;
      --text: #2f3832;
      --nav-ink: #5f6963;
      --muted: #78827c;
      --faint: #a4aca7;
      --line: #e4e9e6;
      --line-strong: #d8dfdb;
      --accent: #1f8a52;
      --accent-soft: #e7f3ec;
      --accent-line: #cce7d7;
      --deep: #113d2a;
      --deep-2: #1e5b3e;
      --blue: #2f6fce;
      --blue-soft: #e7eefb;
      --blue-line: #cbdaf7;
      --hot: #d95367;
      --hot-soft: #fae9ed;
      --hot-line: #f4c9d1;
      --warm: #c47a23;
      --warm-soft: #fff1dc;
      --warm-line: #f2d5a9;
      --cold: #7b8794;
      --cold-soft: #eef2f5;
      --cold-line: #dce4e9;
      --shadow: 0 18px 38px rgba(23,32,27,.08);"""

DARK_VARS = """--bg: #0e1411;
      --panel: #151d18;
      --panel-soft: #1a231e;
      --sidebar-bg: #101713;
      --topbar-bg: rgba(14,20,17,.82);
      --nav-hover: #1c2620;
      --input-bg: #101713;
      --track: #23302a;
      --ink: #e9f0eb;
      --text: #cbd6cf;
      --nav-ink: #a7b3ab;
      --muted: #8da096;
      --faint: #67796f;
      --line: #24312a;
      --line-strong: #304037;
      --accent: #3ecb85;
      --accent-soft: #143423;
      --accent-line: #1f4d33;
      --deep: #0d2f20;
      --deep-2: #1a4b33;
      --blue: #6ea6f4;
      --blue-soft: #16243b;
      --blue-line: #24406b;
      --hot: #f08398;
      --hot-soft: #3a1e26;
      --hot-line: #5c2e3a;
      --warm: #e3a556;
      --warm-soft: #35270f;
      --warm-line: #5a4420;
      --cold: #93a1ad;
      --cold-soft: #212b31;
      --cold-line: #33424c;
      --shadow: 0 18px 38px rgba(0,0,0,.35);"""

# Theme bootstrap + toggle. Served inline and allowed via a CSP sha256 hash,
# so the strict default-src 'self' policy stays intact.
THEME_SCRIPT = (
    "(function(){try{var t=localStorage.getItem('cp-theme');"
    "if(t){document.documentElement.dataset.theme=t;}}catch(e){}"
    "document.addEventListener('DOMContentLoaded',function(){"
    "var b=document.getElementById('theme-toggle');if(!b){return;}"
    "b.addEventListener('click',function(){var d=document.documentElement;"
    "var cur=d.dataset.theme||(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');"
    "var nx=cur==='dark'?'light':'dark';d.dataset.theme=nx;"
    "try{localStorage.setItem('cp-theme',nx);}catch(e){}});});})();"
)
THEME_SCRIPT_HASH = base64.b64encode(hashlib.sha256(THEME_SCRIPT.encode("utf-8")).digest()).decode("ascii")


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


def workspace_switcher() -> str:
    try:
        with db() as conn:
            context = workspace_context(conn)
    except Exception:
        return badge("Demo mode", "status-demo")
    workspace = context.get("workspace") or {}
    workspaces = context.get("workspaces") or []
    if not workspaces:
        return badge("Demo mode", "status-demo")
    selected_id = str(workspace.get("id") or "")
    options = "".join(
        f'<option value="{row["id"]}" {"selected" if str(row["id"]) == selected_id else ""}>{esc(row["name"])}</option>'
        for row in workspaces
    )
    current_user = context.get("current_user") or {}
    return f"""
        <div class="workspace-tools">
          <form method="post" action="/workspace/switch" class="workspace-switch">
            <select name="workspace_id" aria-label="Workspace">{options}</select>
            <button class="btn" type="submit">Switch</button>
          </form>
          <div>{badge(esc(current_user.get('role_label', 'Demo mode')), 'status-demo')}</div>
        </div>
    """


def current_role() -> str:
    try:
        with db() as conn:
            context = workspace_context(conn)
    except Exception:
        return "owner"
    return str((context.get("current_user") or {}).get("role") or "owner")


def nav_groups_for_mode(role: str) -> list[tuple[str, list[tuple[str, str, str]]]]:
    if not clinic_mode():
        return [
            (
                "Workspace",
                [
                    ("/", "Dashboard", "Dashboard"),
                    ("/businesses", "Businesses", "Businesses"),
                    ("/modules", "Modules", "Modules"),
                    ("/agent-builder", "Agent Builder", "Agent Builder"),
                    ("/knowledge", "Knowledge", "Knowledge"),
                ],
            ),
            (
                "Calling",
                [
                    ("/demo-call", "Demo Call", "Demo Call"),
                    ("/real-calling", "Real Calling", "Real Calling"),
                    ("/campaigns", "Campaigns", "Campaigns"),
                    ("/jobs", "Jobs", "Jobs"),
                ],
            ),
            (
                "CRM",
                [
                    ("/leads", "Leads", "Leads"),
                    ("/bookings", "Bookings", "Bookings"),
                    ("/calendar", "Calendar", "Calendar"),
                    ("/calls", "Calls", "Calls"),
                    ("/qa", "QA", "QA"),
                    ("/notifications", "Notifications", "Notifications"),
                ],
            ),
            (
                "Admin",
                [
                    ("/compliance", "Compliance", "Compliance"),
                    ("/admin", "Admin", "Admin"),
                    ("/settings", "Settings", "Settings"),
                ],
            ),
        ]

    workspace_items = [
        ("/", "Dashboard", "Dashboard"),
        ("/businesses", "Businesses", "Businesses"),
        ("/knowledge", "Knowledge", "Knowledge"),
    ]
    if role_allows(role, "manage_agents"):
        workspace_items.append(("/agent-builder", "Agent Builder", "Agent Builder"))
    calling_items = [
        ("/demo-call", "Demo Call", "Demo Call"),
        ("/real-calling", "Real Calling", "Real Calling"),
    ]
    if role_allows(role, "run_jobs"):
        calling_items.append(("/jobs", "Jobs", "Jobs"))
    return [
        ("Workspace", workspace_items),
        ("Calling", calling_items),
        (
            "Clinic",
            [
                ("/bookings", "Bookings", "Bookings"),
                ("/calendar", "Calendar", "Calendar"),
                ("/calls", "Calls", "Call History"),
                ("/leads", "Leads", "Patients/Inquiries"),
                ("/qa", "QA", "Call Quality"),
                ("/notifications", "Notifications", "Alerts"),
            ],
        ),
        ("Admin", [("/compliance", "Compliance", "Compliance"), ("/settings", "Settings", "Settings")]),
    ]


def layout(title_text: str, active: str, content: str) -> str:
    tagline = app_tagline()
    nav_groups = nav_groups_for_mode(current_role())
    nav_html = "".join(
        f'<div class="nav-group"><div class="nav-label">{esc(group)}</div>'
        + "".join(
            f'<a class="{"active" if active == active_key else ""}" href="{href}"><span></span>{esc(label)}</a>'
            for href, active_key, label in items
        )
        + "</div>"
        for group, items in nav_groups
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title_text)} - {APP_NAME}</title>
  <script>{THEME_SCRIPT}</script>
  <style>
    :root {{
      {LIGHT_VARS}
    }}
    @media (prefers-color-scheme: dark) {{
      :root:not([data-theme="light"]) {{
        {DARK_VARS}
      }}
    }}
    :root[data-theme="dark"] {{
      {DARK_VARS}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      color-scheme: light dark;
      font-family: Inter, "Plus Jakarta Sans", Segoe UI, Arial, sans-serif;
      min-height: 100vh;
    }}
    a {{ color: inherit; text-decoration: none; }}
    .shell {{ display: grid; grid-template-columns: 252px 1fr; min-height: 100vh; }}
    .sidebar {{
      border-right: 1px solid var(--line);
      background: var(--sidebar-bg);
      padding: 24px 14px;
      position: sticky;
      top: 0;
      height: 100vh;
      overflow-y: auto;
    }}
    .brand {{ display: flex; gap: 12px; align-items: center; margin: 0 8px 26px; }}
    .mark {{ width: 42px; height: 42px; display: grid; place-items: center; border-radius: 8px; background: var(--deep); color: #c9f1d7; font-weight: 900; }}
    .brand strong {{ display: block; font-size: 16px; }}
    .brand span {{ color: var(--muted); font-size: 12px; line-height: 1.35; }}
    .nav {{ display: grid; gap: 20px; }}
    .nav-group {{ display: grid; gap: 5px; }}
    .nav-label {{ padding: 0 10px 5px; color: var(--faint); font-size: 10px; font-weight: 850; letter-spacing: .08em; text-transform: uppercase; }}
    .nav a {{ display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 8px; color: var(--nav-ink); font-size: 14px; font-weight: 750; }}
    .nav a span {{ width: 8px; height: 8px; border-radius: 3px; border: 1px solid var(--line-strong); background: var(--panel); }}
    .nav a:hover {{ background: var(--nav-hover); color: var(--ink); }}
    .nav a.active {{ background: var(--accent-soft); color: var(--accent); }}
    .nav a.active span {{ border-color: var(--accent); background: var(--accent); }}
    .main {{ min-width: 0; }}
    .topbar {{ min-height: 70px; display: flex; justify-content: space-between; align-items: center; padding: 16px 28px; border-bottom: 1px solid var(--line); background: var(--topbar-bg); backdrop-filter: blur(14px); }}
    .topbar p {{ margin: 3px 0 0; color: var(--muted); font-size: 13px; }}
    .topbar-right {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }}
    .workspace-tools {{ display:flex; align-items:center; justify-content:flex-end; gap:10px; flex-wrap:wrap; }}
    .workspace-switch {{ display:flex; align-items:center; gap:8px; }}
    .workspace-switch select {{ min-width:190px; max-width:260px; }}
    main {{ max-width: 1360px; margin: 0 auto; padding: 26px; }}
    h1 {{ margin: 0; font-size: 30px; letter-spacing: 0; }}
    h2 {{ margin: 0; font-size: 17px; }}
    h3 {{ margin: 0; font-size: 15px; }}
    p {{ line-height: 1.65; }}
    .muted {{ color: var(--muted); }}
    .hero {{ padding: 24px; border: 1px solid rgba(17,61,42,.22); border-radius: 8px; color: #fff; background: linear-gradient(145deg, var(--deep), var(--deep-2)); box-shadow: var(--shadow); }}
    .hero p {{ max-width: 880px; color: rgba(255,255,255,.78); }}
    .grid {{ display: grid; gap: 16px; }}
    .metrics {{ grid-template-columns: repeat(4, minmax(0,1fr)); margin-top: 18px; }}
    .two {{ grid-template-columns: 1.15fr .85fr; }}
    .three {{ grid-template-columns: repeat(3, minmax(0,1fr)); }}
    .four {{ grid-template-columns: repeat(4, minmax(0,1fr)); }}
    .cards {{ grid-template-columns: repeat(3, minmax(0,1fr)); }}
    .panel {{ border: 1px solid var(--line); border-radius: 8px; background: var(--panel); box-shadow: var(--shadow); }}
    .pad {{ padding: 20px; }}
    .metric {{ min-height: 116px; padding: 18px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); box-shadow: var(--shadow); }}
    .metric span {{ display:block; color: var(--muted); font-size: 13px; font-weight: 750; }}
    .metric strong {{ display:block; margin-top: 9px; font-size: 30px; }}
    .metric.good {{ background: linear-gradient(145deg, var(--deep), var(--deep-2)); border-color: transparent; color: #fff; }}
    .metric.good span {{ color: rgba(255,255,255,.76); }}
    .hot strong {{ color: var(--hot); }} .warm strong {{ color: var(--warm); }} .cold strong {{ color: var(--cold); }} .good strong {{ color: inherit; }}
    .row {{ display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap; }}
    .actions {{ display: flex; gap: 9px; flex-wrap: wrap; align-items: center; }}
    .btn {{ border: 1px solid var(--line-strong); border-radius: 8px; background: var(--panel); color: var(--ink); padding: 10px 14px; min-height: 40px; font-weight: 800; cursor: pointer; display: inline-flex; align-items:center; justify-content:center; }}
    .btn:hover {{ background: var(--panel-soft); }}
    .btn.primary {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
    .btn.danger {{ color: var(--hot); }}
    .badge {{ display:inline-flex; min-height:24px; align-items:center; border-radius:999px; padding:3px 9px; font-size:12px; font-weight:850; border:1px solid transparent; }}
    .temp-hot {{ background: var(--hot-soft); color: var(--hot); border-color: var(--hot-line); }}
    .temp-warm {{ background: var(--warm-soft); color: var(--warm); border-color: var(--warm-line); }}
    .temp-cold {{ background: var(--cold-soft); color: var(--cold); border-color: var(--cold-line); }}
    .status-active, .status-won, .status-sent, .status-connected, .status-completed, .status-ready {{ background: var(--accent-soft); color: var(--accent); border-color: var(--accent-line); }}
    .status-new, .status-demo, .status-requested, .status-draft, .status-queued {{ background: var(--blue-soft); color: var(--blue); border-color: var(--blue-line); }}
    .status-follow_up, .status-contacted {{ background: var(--warm-soft); color: var(--warm); border-color: var(--warm-line); }}
    .status-lost, .status-missing, .status-suppressed, .status-failed {{ background: var(--hot-soft); color: var(--hot); border-color: var(--hot-line); }}
    .list .item {{ display:block; padding: 15px 20px; border-top: 1px solid var(--line); }}
    .list .item:first-child {{ border-top: 0; }}
    .list .item:hover {{ background: var(--panel-soft); }}
    .mini {{ border:1px solid var(--line); border-radius: 8px; padding: 14px; background: var(--panel-soft); }}
    .mini span {{ color: var(--muted); font-size: 12px; font-weight: 800; display:block; }}
    .mini strong {{ display:block; margin-top:5px; }}
    table {{ width:100%; border-collapse:collapse; min-width: 940px; }}
    th {{ text-align:left; color: var(--muted); font-size:12px; text-transform:uppercase; padding:13px 16px; background:var(--panel-soft); }}
    td {{ padding:15px 16px; border-top:1px solid var(--line); vertical-align:middle; }}
    tr:hover td {{ background: var(--panel-soft); }}
    .table-wrap {{ overflow-x:auto; }}
    input, textarea, select {{ width:100%; border:1px solid var(--line-strong); border-radius:8px; padding:11px 12px; background:var(--input-bg); color:var(--ink); font:inherit; }}
    input[type="checkbox"] {{ width:auto; }}
    .checkline {{ display:flex; grid-template-columns:none; align-items:center; gap:10px; font-weight:800; }}
    option {{ color:var(--ink); }}
    textarea {{ min-height: 150px; resize:vertical; line-height:1.55; }}
    label {{ display:grid; gap:7px; font-size:14px; font-weight:800; }}
    .form-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:15px; }}
    .full {{ grid-column: 1 / -1; }}
    pre {{ white-space:pre-wrap; overflow:auto; background:#102319; color:#e8fff0; border-radius:8px; padding:16px; line-height:1.6; }}
    .bar {{ height:9px; border-radius:999px; overflow:hidden; background:var(--track); }}
    .bar span {{ display:block; height:100%; background:linear-gradient(90deg, var(--accent), var(--blue)); }}
    .dashboard-grid {{ display:grid; grid-template-columns:minmax(0,1.7fr) minmax(320px,.9fr); gap:16px; align-items:start; }}
    .chart-bars {{ display:flex; align-items:flex-end; justify-content:space-between; gap:12px; height:188px; margin-top:18px; }}
    .chart-bar {{ flex:1; min-width:20px; display:flex; flex-direction:column; align-items:center; justify-content:flex-end; gap:9px; height:100%; }}
    .chart-bar i {{ display:block; width:100%; max-width:34px; border-radius:8px 8px 3px 3px; background:var(--accent); }}
    .chart-bar span {{ font-size:12px; color:var(--muted); font-weight:750; }}
    .callout {{ border-radius:8px; background:linear-gradient(145deg,var(--deep),var(--deep-2)); color:#fff; padding:20px; box-shadow:var(--shadow); }}
    .callout .muted {{ color:rgba(255,255,255,.74); }}
    .avatar {{ width:34px; height:34px; border-radius:8px; display:grid; place-items:center; flex:none; background:var(--accent-soft); color:var(--accent); font-weight:900; }}
    .entity-card {{ display:grid; gap:16px; min-height:250px; }}
    .entity-head {{ display:flex; gap:12px; align-items:flex-start; justify-content:space-between; }}
    .entity-title {{ display:flex; gap:12px; min-width:0; align-items:center; }}
    .entity-title h2, .entity-title strong {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .kicker {{ color:var(--faint); font-size:11px; font-weight:850; letter-spacing:.08em; text-transform:uppercase; }}
    .scorebar {{ display:grid; gap:6px; min-width:120px; }}
    .scorebar-track {{ height:8px; border-radius:999px; overflow:hidden; background:var(--track); }}
    .scorebar-track span {{ display:block; height:100%; border-radius:inherit; background:linear-gradient(90deg,var(--accent),var(--deep-2)); }}
    .progress-ring {{ display:grid; place-items:center; min-height:220px; }}
    .progress-ring svg {{ max-width:230px; width:100%; height:auto; }}
    @media (max-width: 1100px) {{
      .shell {{ grid-template-columns:1fr; }}
      .sidebar {{ height:auto; position:static; }}
      .nav {{ grid-template-columns: repeat(4, minmax(180px, 1fr)); overflow-x:auto; align-items:start; }}
      .metrics, .two, .three, .four, .cards, .form-grid, .dashboard-grid {{ grid-template-columns:1fr; }}
      main, .topbar {{ padding-left:16px; padding-right:16px; }}
    }}
    @media (max-width: 640px) {{
      .metrics {{ grid-template-columns:1fr; }}
      .topbar {{ align-items:flex-start; gap:12px; flex-direction:column; }}
      .workspace-tools, .workspace-switch {{ width:100%; justify-content:flex-start; }}
      .workspace-switch select {{ flex:1; min-width:0; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand"><div class="mark">CP</div><div><strong>{APP_NAME}</strong><span>{esc(tagline)}</span></div></div>
      <nav class="nav">{nav_html}</nav>
    </aside>
    <div class="main">
      <header class="topbar">
        <div><strong>{APP_NAME}</strong><p>{esc(tagline)}</p></div>
        <div class="topbar-right">
          {workspace_switcher()}
          <button id="theme-toggle" class="btn" type="button" title="Switch light/dark theme" aria-label="Switch light or dark theme">&#127769;</button>
        </div>
      </header>
      <main>{content}</main>
    </div>
  </div>
</body>
</html>"""

def metric(label: str, value: Any, kind: str = "") -> str:
    return f'<div class="metric {esc(kind)}"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>'

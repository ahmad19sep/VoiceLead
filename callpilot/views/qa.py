from __future__ import annotations

from .layout import layout, metric
from ..repositories import get_qa_evaluations
from ..storage import db
from ..ui import badge
from ..utils import esc, format_dt, from_json, title


def qa_badge(status: str) -> str:
    kind = {
        "pass": "status-active",
        "review": "status-follow_up",
        "fail": "status-missing",
    }.get(status, "status-new")
    return badge(title(status), kind)


def render_qa(query: dict[str, list[str]]) -> str:
    selected = query.get("status", ["all"])[0]
    with db() as conn:
        rows = get_qa_evaluations(conn, selected)
        all_rows = get_qa_evaluations(conn)
    counts = {
        "total": len(all_rows),
        "pass": sum(1 for row in all_rows if row["qa_status"] == "pass"),
        "review": sum(1 for row in all_rows if row["qa_status"] == "review"),
        "fail": sum(1 for row in all_rows if row["qa_status"] == "fail"),
        "avg": round(sum(int(row["qa_score"] or 0) for row in all_rows) / len(all_rows)) if all_rows else 0,
    }
    options = "".join(
        f'<option value="{value}" {"selected" if selected == value else ""}>{label}</option>'
        for value, label in [("all", "All"), ("pass", "Pass"), ("review", "Review"), ("fail", "Fail")]
    )
    table_rows = ""
    for row in rows:
        findings = from_json(row.get("findings"), [])
        failures = from_json(row.get("critical_failures"), [])
        issue_preview = failures[:1] or findings[:1] or ["No issues detected."]
        table_rows += f"""
        <tr>
          <td>
            <div style="display:flex;align-items:center;gap:12px;">
              <span class="avatar">{esc((row['business_name'] or 'Q')[:1].upper())}</span>
              <div><strong>{esc(row['business_name'] or 'Unknown')}</strong><div class="muted">{esc(row['business_type'] or '')}</div></div>
            </div>
          </td>
          <td>{esc(row['customer_name'] or 'Unknown')}</td>
          <td>
            <div class="scorebar">
              <div class="row"><strong>{row['qa_score']}/100</strong>{qa_badge(row['qa_status'])}</div>
              <div class="scorebar-track"><span style="width:{min(100, int(row['qa_score'] or 0))}%"></span></div>
            </div>
          </td>
          <td>{esc(issue_preview[0])}</td>
          <td>{esc(row['provider'] or '')}</td>
          <td>{format_dt(row['evaluated_at'])}</td>
          <td><a class="btn" href="/leads/{row['lead_id']}">Lead</a></td>
        </tr>
        """
    content = f"""
    <section class="row">
      <div><h1>QA Review</h1><p class="muted">Call evaluation for safety, workflow integrity, language handling, and actionable follow-up.</p></div>
      <a class="btn" href="/api/qa/evaluations">QA JSON</a>
    </section>
    <section class="grid metrics">
      {metric('Evaluations', counts['total'])}
      {metric('Average QA', counts['avg'])}
      {metric('Pass', counts['pass'], 'good')}
      {metric('Needs Review', counts['review'], 'warm')}
      {metric('Fail', counts['fail'], 'hot')}
    </section>
    <form method="get" class="panel pad actions" style="margin-top:18px;">
      <select style="max-width:180px" name="status">{options}</select>
      <button class="btn primary" type="submit">Filter</button>
    </form>
    <section class="panel table-wrap" style="margin-top:18px;">
      <table>
        <thead><tr><th>Business</th><th>Customer</th><th>QA Score</th><th>Top Finding</th><th>Provider</th><th>Evaluated</th><th>Open</th></tr></thead>
        <tbody>{table_rows or '<tr><td colspan="7">No QA evaluations yet.</td></tr>'}</tbody>
      </table>
    </section>
    """
    return layout("QA Review", "QA", content)

from __future__ import annotations

from .layout import layout, metric
from ..jobs import get_jobs
from ..storage import db
from ..ui import badge, status_badge
from ..utils import esc, format_dt, from_json, title


def render_jobs(query: dict[str, list[str]]) -> str:
    selected = query.get("status", ["all"])[0]
    ran = query.get("ran", [""])[0]
    with db() as conn:
        rows = get_jobs(conn, selected)
        all_rows = get_jobs(conn, "all", 500)
    counts = {
        "total": len(all_rows),
        "pending": sum(1 for row in all_rows if row["status"] == "pending"),
        "completed": sum(1 for row in all_rows if row["status"] == "completed"),
        "failed": sum(1 for row in all_rows if row["status"] == "failed"),
        "running": sum(1 for row in all_rows if row["status"] == "running"),
    }
    options = "".join(
        f'<option value="{value}" {"selected" if selected == value else ""}>{label}</option>'
        for value, label in [
            ("all", "All"),
            ("pending", "Pending"),
            ("running", "Running"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ]
    )
    table_rows = ""
    for row in rows:
        payload = from_json(row.get("payload"), {})
        result = from_json(row.get("result"), {})
        preview = result.get("reason") or result.get("status") or row.get("error") or payload
        table_rows += f"""
        <tr>
          <td><strong>{esc(row['job_type'])}</strong><div class="muted">{esc(row['resource_type'] or '')} #{esc(row['resource_id'] or '')}</div></td>
          <td>{status_badge(row['status'])}</td>
          <td>{row['attempts']}/{row['max_attempts']}</td>
          <td>{format_dt(row['scheduled_at'])}</td>
          <td>{format_dt(row['finished_at'])}</td>
          <td>{esc(preview)}</td>
        </tr>
        """
    content = f"""
    <section class="row">
      <div><h1>Jobs</h1><p class="muted">Manual worker queue for campaign preparation, post-call processing, retries, and future provider tasks.</p></div>
      {badge('Manual runner', 'status-demo')}
    </section>
    {'<section class="panel pad" style="margin-top:16px;">'+badge('Ran','status-active')+' '+esc(ran)+' due jobs processed.</section>' if ran else ''}
    <section class="grid metrics">
      {metric('Jobs', counts['total'])}
      {metric('Pending', counts['pending'], 'warm')}
      {metric('Running', counts['running'])}
      {metric('Completed', counts['completed'], 'good')}
      {metric('Failed', counts['failed'], 'hot' if counts['failed'] else '')}
    </section>
    <section class="panel pad" style="margin-top:18px;">
      <form method="post" action="/jobs/run" class="actions">
        <button class="btn primary" type="submit">Run Due Jobs</button>
        <a class="btn" href="/api/jobs">Jobs JSON</a>
      </form>
    </section>
    <form method="get" class="panel pad actions" style="margin-top:18px;">
      <select style="max-width:180px" name="status">{options}</select>
      <button class="btn" type="submit">Filter</button>
    </form>
    <section class="panel table-wrap" style="margin-top:18px;">
      <table><thead><tr><th>Job</th><th>Status</th><th>Attempts</th><th>Scheduled</th><th>Finished</th><th>Result</th></tr></thead><tbody>{table_rows or '<tr><td colspan="6">No jobs yet.</td></tr>'}</tbody></table>
    </section>
    """
    return layout("Jobs", "Jobs", content)

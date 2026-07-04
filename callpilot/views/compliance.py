from __future__ import annotations

from .layout import layout
from ..compliance import get_audit_logs, get_consent_records, get_dnc_entries, get_staff_contacts, get_workspace
from ..repositories import get_businesses
from ..storage import db
from ..ui import badge, status_badge
from ..utils import esc, format_dt, from_json


def render_compliance(query: dict[str, list[str]]) -> str:
    saved = query.get("saved", [""])[0]
    with db() as conn:
        workspace = get_workspace(conn)
        businesses = get_businesses(conn)
        staff = get_staff_contacts(conn)
        consents = get_consent_records(conn)
        dnc_entries = get_dnc_entries(conn)
        audits = get_audit_logs(conn)

    business_options = "".join(
        f'<option value="{b["id"]}">{esc(b["name"])} - {esc(b["business_type"])}</option>' for b in businesses
    )
    staff_rows = "".join(
        f"""
        <tr>
          <td><strong>{esc(row['name'])}</strong></td>
          <td>{esc(row['business_name'] or 'Workspace')}</td>
          <td>{esc(row['role'] or '')}</td>
          <td>{esc(row['phone'] or '')}</td>
          <td>{esc(row['email'] or '')}</td>
          <td>{'Yes' if row['receives_handoff'] else 'No'}</td>
        </tr>
        """
        for row in staff
    )
    consent_rows = "".join(
        f"""
        <tr>
          <td>{esc(row['customer_phone'])}</td>
          <td>{esc(row['business_name'] or 'Any')}</td>
          <td>{esc(row['consent_type'])}</td>
          <td>{esc(row['source'] or '')}</td>
          <td>{status_badge(row['status'])}</td>
          <td>{format_dt(row['created_at'])}</td>
        </tr>
        """
        for row in consents
    )
    dnc_rows = "".join(
        f"""
        <tr>
          <td>{esc(row['customer_phone'])}</td>
          <td>{esc(row['reason'] or '')}</td>
          <td>{esc(row['source'] or '')}</td>
          <td>{status_badge(row['status'])}</td>
          <td>{format_dt(row['created_at'])}</td>
        </tr>
        """
        for row in dnc_entries
    )
    audit_rows = "".join(
        f"""
        <tr>
          <td>{format_dt(row['created_at'])}</td>
          <td>{esc(row['actor_type'])}</td>
          <td>{esc(row['action'])}</td>
          <td>{esc(row['resource_type'])}</td>
          <td>{esc(from_json(row['metadata'], {}))}</td>
        </tr>
        """
        for row in audits
    )
    content = f"""
    <section class="hero">
      <div class="row">
        <div>
          <h1>Compliance Center</h1>
          <p>Workspace, staff handoff, consent, Do Not Call, and audit controls for the production calling roadmap.</p>
        </div>
        {badge('Workspace Active', 'status-active')}
      </div>
      <div class="grid four" style="margin-top:14px;">
        <div class="mini"><span>Workspace</span><strong>{esc((workspace or {}).get('name', 'Default Workspace'))}</strong></div>
        <div class="mini"><span>Plan</span><strong>{esc((workspace or {}).get('plan', 'demo'))}</strong></div>
        <div class="mini"><span>Timezone</span><strong>{esc((workspace or {}).get('timezone', 'Asia/Karachi'))}</strong></div>
        <div class="mini"><span>Status</span><strong>{esc((workspace or {}).get('status', 'active'))}</strong></div>
      </div>
    </section>
    {'<section class="panel pad" style="margin-top:16px;">'+badge('Saved','status-active')+' '+esc(saved)+'</section>' if saved else ''}
    <section class="grid two" style="margin-top:18px;">
      <form method="post" action="/compliance/consent" class="panel pad">
        <h2>Record Outbound Consent</h2>
        <div class="form-grid" style="margin-top:14px;">
          <label>Business<select name="business_id">{business_options}</select></label>
          <label>Phone<input name="phone" placeholder="+923001234567" required></label>
          <label>Consent type<input name="consent_type" value="outbound_call"></label>
          <label>Source<input name="source" value="operator"></label>
          <label class="full">Proof<textarea name="proof">Operator confirmed caller consent for outbound test call.</textarea></label>
        </div>
        <div class="actions" style="margin-top:14px;"><button class="btn primary" type="submit">Record Consent</button></div>
      </form>
      <form method="post" action="/compliance/dnc" class="panel pad">
        <h2>Add Do Not Call</h2>
        <div class="form-grid" style="margin-top:14px;">
          <label>Phone<input name="phone" placeholder="+923001234567" required></label>
          <label>Source<input name="source" value="operator"></label>
          <label class="full">Reason<textarea name="reason">Customer opted out of outbound calls.</textarea></label>
        </div>
        <div class="actions" style="margin-top:14px;"><button class="btn danger" type="submit">Add To DNC</button></div>
      </form>
    </section>
    <section class="panel table-wrap" style="margin-top:18px;">
      <div class="pad"><h2>Staff Handoff Contacts</h2></div>
      <table><thead><tr><th>Name</th><th>Business</th><th>Role</th><th>Phone</th><th>Email</th><th>Receives Handoff</th></tr></thead><tbody>{staff_rows or '<tr><td colspan="6">No staff contacts yet.</td></tr>'}</tbody></table>
    </section>
    <section class="grid two" style="margin-top:18px;">
      <div class="panel table-wrap">
        <div class="pad"><h2>Consent Records</h2></div>
        <table><thead><tr><th>Phone</th><th>Business</th><th>Type</th><th>Source</th><th>Status</th><th>Created</th></tr></thead><tbody>{consent_rows or '<tr><td colspan="6">No consent records yet.</td></tr>'}</tbody></table>
      </div>
      <div class="panel table-wrap">
        <div class="pad"><h2>Do Not Call</h2></div>
        <table><thead><tr><th>Phone</th><th>Reason</th><th>Source</th><th>Status</th><th>Created</th></tr></thead><tbody>{dnc_rows or '<tr><td colspan="5">No DNC entries.</td></tr>'}</tbody></table>
      </div>
    </section>
    <section class="panel table-wrap" style="margin-top:18px;">
      <div class="pad"><h2>Audit Log</h2></div>
      <table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Resource</th><th>Metadata</th></tr></thead><tbody>{audit_rows or '<tr><td colspan="5">No audit records yet.</td></tr>'}</tbody></table>
    </section>
    """
    return layout("Compliance", "Compliance", content)

from __future__ import annotations

from .errors import render_not_found
from .layout import layout, metric
from ..knowledge import (
    get_document_items,
    get_knowledge_document,
    get_knowledge_documents,
    knowledge_stats,
    search_knowledge,
)
from ..repositories import get_businesses
from ..storage import db
from ..ui import badge, status_badge
from ..utils import esc, format_dt, title


def render_knowledge(query: dict[str, list[str]]) -> str:
    selected = int(query.get("business_id", ["0"])[0] or 0)
    q = query.get("q", [""])[0]
    language = query.get("language", ["en"])[0]
    saved = query.get("saved", [""])[0]
    with db() as conn:
        businesses = get_businesses(conn)
        if not selected and businesses:
            selected = int(businesses[0]["id"])
        docs = get_knowledge_documents(conn, selected or None)
        stats = knowledge_stats(conn, selected or None)
        results = search_knowledge(conn, selected, q, language) if selected and q else []
    business_options = "".join(
        f'<option value="{b["id"]}" {"selected" if selected == b["id"] else ""}>{esc(b["name"])} - {esc(b["business_type"])}</option>'
        for b in businesses
    )
    doc_rows = "".join(
        f"""
        <tr>
          <td>
            <div style="display:flex;align-items:center;gap:12px;">
              <span class="avatar">{esc((row['title'] or 'K')[:1].upper())}</span>
              <div><strong>{esc(row['title'])}</strong><div class="muted">{esc(row['source_type'])} v{row['version']}</div></div>
            </div>
          </td>
          <td><strong>{esc(row['business_name'])}</strong></td>
          <td>{status_badge(row['status'])}</td>
          <td>{row['item_count']}</td>
          <td>{esc(row['approved_by'] or 'system')}</td>
          <td>{format_dt(row['updated_at'])}</td>
          <td><a class="btn" href="/knowledge/{row['id']}">Open</a></td>
        </tr>
        """
        for row in docs
    )
    result_rows = "".join(
        f"""
        <div class="item">
          <div class="row"><strong>{esc(row['question'])}</strong>{badge('Score '+str(row['match_score']), 'status-active')}</div>
          <div class="muted">{esc(row['answer'])}</div>
          <small>{esc(row.get('document_title') or row.get('source') or 'Knowledge base')} - {esc(row.get('category') or 'General')} - {esc(row.get('answer_language') or row.get('language') or 'en')} {'- translated fallback' if row.get('translated') else ''}</small>
        </div>
        """
        for row in results
    )
    content = f"""
    <section class="row">
      <div><h1>Knowledge</h1><p class="muted">Versioned business knowledge used by call analysis, agent answers, and QA review.</p></div>
      {badge('Approved answers only', 'status-active')}
    </section>
    {'<section class="panel pad" style="margin-top:16px;">'+badge('Saved','status-active')+' '+esc(saved)+'</section>' if saved else ''}
    <section class="callout" style="margin-top:18px;">
      <div class="row">
        <div>
          <div class="kicker" style="color:rgba(255,255,255,.7);">Knowledge safety</div>
          <h2 style="margin-top:6px;">Only approved knowledge is used for answers.</h2>
          <p class="muted" style="margin-bottom:0;">Manual notes, documents, URLs, and policies are versioned before they enter agent context.</p>
        </div>
        <a class="btn primary" style="background:#fff;color:var(--deep);border-color:#fff;" href="/api/knowledge/search?business_id={selected}&q={esc(q)}&language={esc(language)}">Search API</a>
      </div>
    </section>
    <section class="grid metrics">
      {metric('Documents', stats['documents'])}
      {metric('Items', stats['items'])}
      {metric('Approved', stats['approved_items'], 'good')}
      {metric('Stale >90d', stats['stale_documents'], 'warm' if stats['stale_documents'] else '')}
    </section>
    <section class="grid two" style="margin-top:18px;">
      <form class="panel pad" method="post" action="/knowledge/ingest">
        <h2>Add Knowledge</h2>
        <div class="form-grid" style="margin-top:14px;">
          <label>Business<select name="business_id">{business_options}</select></label>
          <label>Title<input name="title" value="Operations knowledge" required></label>
          <label>Source type<select name="source_type"><option value="manual">Manual note</option><option value="document">Document</option><option value="url">URL</option><option value="policy">Policy</option></select></label>
          <label>Source / reference<input name="source" placeholder="PDF name, URL, SOP owner"></label>
          <label class="full">Content<textarea name="content" rows="9" placeholder="Question | Answer | Category | Tags | Language | Translation group&#10;What hours are you open? | Monday to Friday 9 AM to 6 PM | Hours | hours,schedule | en | hours"></textarea></label>
        </div>
        <div class="actions" style="margin-top:14px;"><button class="btn primary" type="submit">Approve And Add</button></div>
      </form>
      <aside class="panel pad">
        <h2>Search Approved Knowledge</h2>
        <form method="get" class="actions" style="margin-top:14px;">
          <select style="max-width:260px" name="business_id">{business_options}</select>
          <select style="max-width:120px" name="language">
            <option value="en" {"selected" if language == "en" else ""}>English</option>
            <option value="ur" {"selected" if language == "ur" else ""}>Urdu</option>
            <option value="ar" {"selected" if language == "ar" else ""}>Arabic</option>
          </select>
          <input name="q" value="{esc(q)}" placeholder="insurance, refund, booking, emergency">
          <button class="btn" type="submit">Search</button>
        </form>
        <div class="list" style="margin-top:14px;">{result_rows or '<div class="item muted">Search results appear here.</div>'}</div>
      </aside>
    </section>
    <section class="panel table-wrap" style="margin-top:18px;">
      <table><thead><tr><th>Document</th><th>Business</th><th>Status</th><th>Items</th><th>Approved By</th><th>Updated</th><th>Open</th></tr></thead><tbody>{doc_rows or '<tr><td colspan="7">No knowledge documents yet.</td></tr>'}</tbody></table>
    </section>
    """
    return layout("Knowledge", "Knowledge", content)


def render_knowledge_document(document_id: int) -> str:
    with db() as conn:
        document = get_knowledge_document(conn, document_id)
        if not document:
            return render_not_found()
        items = get_document_items(conn, document_id)
    rows = "".join(
        f"""
        <tr>
          <td><strong>{esc(item['question'])}</strong><div class="muted">{esc(item['category'] or 'General')}</div></td>
          <td>{esc(item['answer'])}</td>
          <td>{esc(item['tags'] or '')}</td>
          <td>{esc(item['language'] or 'en')}</td>
          <td>{esc(item['translation_group_id'] or '')}</td>
          <td>{status_badge(item['status'] or 'approved')}</td>
        </tr>
        """
        for item in items
    )
    content = f"""
    <a class="btn" href="/knowledge?business_id={document['business_id']}">Back to Knowledge</a>
    <section class="hero" style="margin-top:16px;">
      <div class="row">
        <div><h1>{esc(document['title'])}</h1><p>{esc(document['business_name'])} - {esc(title(document['source_type']))} v{document['version']}</p></div>
        {status_badge(document['status'])}
      </div>
      <div class="grid four" style="margin-top:14px;">
        <div class="mini"><span>Items</span><strong>{document['item_count']}</strong></div>
        <div class="mini"><span>Approved By</span><strong>{esc(document['approved_by'] or 'system')}</strong></div>
        <div class="mini"><span>Approved</span><strong>{format_dt(document['approved_at'])}</strong></div>
        <div class="mini"><span>Source</span><strong>{esc(document['source'] or 'Not provided')}</strong></div>
      </div>
    </section>
    <section class="panel table-wrap" style="margin-top:18px;">
      <table><thead><tr><th>Question</th><th>Answer</th><th>Tags</th><th>Language</th><th>Translation Group</th><th>Status</th></tr></thead><tbody>{rows or '<tr><td colspan="6">No items attached.</td></tr>'}</tbody></table>
    </section>
    """
    return layout(document["title"], "Knowledge", content)

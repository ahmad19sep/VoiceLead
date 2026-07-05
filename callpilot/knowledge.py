from __future__ import annotations

import hashlib
import re
import sqlite3
from typing import Any

from .compliance import active_workspace_id, default_workspace_id
from .storage import row_dict
from .utils import now


STALE_DAYS = 90
SUPPORTED_KNOWLEDGE_LANGUAGES = {"en", "ur", "ar"}


def _words(value: str) -> set[str]:
    return {word for word in re.findall(r"\w+", value.lower(), flags=re.UNICODE) if len(word) > 1}


def normalize_language(value: str | None) -> str:
    clean = (value or "en").strip().lower()
    aliases = {
        "english": "en",
        "urdu": "ur",
        "roman urdu": "ur",
        "arabic": "ar",
        "عربي": "ar",
        "العربية": "ar",
    }
    clean = aliases.get(clean, clean)
    return clean if clean in SUPPORTED_KNOWLEDGE_LANGUAGES else "en"


def parse_knowledge_content(content: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    lines = [line.strip() for line in (content or "").splitlines() if line.strip()]
    if len(lines) > 1 and any("|" in line for line in lines):
        records = lines
    else:
        records = [part.strip() for part in re.split(r"\n\s*\n", content or "") if part.strip()] or lines
    for idx, paragraph in enumerate(records, 1):
        line = " ".join(paragraph.split())
        parts = [part.strip() for part in line.split("|")]
        if len(parts) >= 2:
            question = parts[0]
            answer = parts[1]
            category = parts[2] if len(parts) > 2 else "General"
            tags = parts[3] if len(parts) > 3 else category.lower()
            language = normalize_language(parts[4] if len(parts) > 4 else "en")
            translation_group_id = parts[5] if len(parts) > 5 else ""
        else:
            question = f"Knowledge note {idx}"
            answer = line
            category = "Policy"
            tags = "policy"
            language = "en"
            translation_group_id = ""
        if question and answer:
            items.append(
                {
                    "question": question,
                    "answer": answer,
                    "category": category,
                    "tags": tags,
                    "language": language,
                    "translation_group_id": translation_group_id,
                }
            )
    return items


def next_document_version(conn: sqlite3.Connection, business_id: int, title: str) -> int:
    row = conn.execute(
        "select max(version) as version from knowledge_documents where business_id = ? and lower(title) = lower(?)",
        (business_id, title),
    ).fetchone()
    return int(row["version"] or 0) + 1


def ingest_knowledge_document(
    conn: sqlite3.Connection,
    business_id: int,
    title: str,
    source_type: str,
    source: str,
    content: str,
    approved_by: str = "operator",
    workspace_id: int | None = None,
) -> dict[str, Any]:
    items = parse_knowledge_content(content)
    if not items:
        return {"success": False, "error": "No knowledge items found."}
    workspace_id = active_workspace_id(conn, workspace_id)
    business = conn.execute(
        "select id, workspace_id from businesses where id = ? and workspace_id = ?",
        (business_id, workspace_id),
    ).fetchone()
    if not business:
        return {"success": False, "error": "Business not found."}
    workspace_id = business["workspace_id"] or workspace_id
    timestamp = now()
    clean_title = (title or "Knowledge document").strip()
    version = next_document_version(conn, business_id, clean_title)
    checksum = hashlib.sha256((content or "").encode("utf-8")).hexdigest()
    document_id = conn.execute(
        """
        insert into knowledge_documents (
            workspace_id, business_id, title, source_type, source, checksum, version,
            status, item_count, approved_by, approved_at, created_at, updated_at
        )
        values (?, ?, ?, ?, ?, ?, ?, 'approved', ?, ?, ?, ?, ?)
        """,
        (
            workspace_id,
            business_id,
            clean_title,
            source_type or "manual",
            source,
            checksum,
            version,
            len(items),
            approved_by,
            timestamp,
            timestamp,
            timestamp,
        ),
    ).lastrowid
    for item in items:
        conn.execute(
            """
            insert into knowledge_base (
                business_id, document_id, question, answer, category, tags, source,
                language, translation_group_id, version, status, approved_at, updated_at, created_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'approved', ?, ?, ?)
            """,
            (
                business_id,
                document_id,
                item["question"],
                item["answer"],
                item.get("category"),
                item.get("tags"),
                source or source_type or "manual",
                item.get("language") or "en",
                item.get("translation_group_id") or None,
                version,
                timestamp,
                timestamp,
                timestamp,
            ),
        )
    return {"success": True, "document_id": document_id, "version": version, "items": len(items)}


def get_knowledge_documents(
    conn: sqlite3.Connection,
    business_id: int | None = None,
    workspace_id: int | None = None,
) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    sql = """
        select knowledge_documents.*, businesses.name as business_name
        from knowledge_documents
        left join businesses on businesses.id = knowledge_documents.business_id
    """
    args: list[Any] = [workspace_id]
    sql += " where knowledge_documents.workspace_id = ?"
    if business_id:
        sql += " and knowledge_documents.business_id = ?"
        args.append(business_id)
    sql += " order by datetime(knowledge_documents.updated_at) desc, knowledge_documents.id desc"
    return [dict(row) for row in conn.execute(sql, args).fetchall()]


def get_knowledge_document(
    conn: sqlite3.Connection,
    document_id: int,
    workspace_id: int | None = None,
) -> dict[str, Any] | None:
    workspace_id = active_workspace_id(conn, workspace_id)
    row = conn.execute(
        """
        select knowledge_documents.*, businesses.name as business_name, businesses.business_type
        from knowledge_documents
        left join businesses on businesses.id = knowledge_documents.business_id
        where knowledge_documents.id = ? and knowledge_documents.workspace_id = ?
        """,
        (document_id, workspace_id),
    ).fetchone()
    return row_dict(row)


def get_document_items(
    conn: sqlite3.Connection,
    document_id: int,
    workspace_id: int | None = None,
) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    rows = conn.execute(
        """
        select knowledge_base.*
        from knowledge_base
        join knowledge_documents on knowledge_documents.id = knowledge_base.document_id
        where knowledge_base.document_id = ? and knowledge_documents.workspace_id = ?
        order by knowledge_base.id
        """,
        (document_id, workspace_id),
    ).fetchall()
    return [dict(row) for row in rows]


def search_knowledge(
    conn: sqlite3.Connection,
    business_id: int,
    query: str,
    caller_language: str | None = "en",
    limit: int = 12,
    workspace_id: int | None = None,
) -> list[dict[str, Any]]:
    terms = _words(query or "")
    if not terms:
        return []
    requested_language = normalize_language(caller_language)
    workspace_id = active_workspace_id(conn, workspace_id)
    rows = conn.execute(
        """
        select knowledge_base.*, knowledge_documents.title as document_title
        from knowledge_base
        left join knowledge_documents on knowledge_documents.id = knowledge_base.document_id
        join businesses on businesses.id = knowledge_base.business_id
        where knowledge_base.business_id = ?
          and businesses.workspace_id = ?
          and coalesce(knowledge_base.status, 'approved') = 'approved'
        """,
        (business_id, workspace_id),
    ).fetchall()
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        item = dict(row)
        text = " ".join(
            str(item.get(field) or "")
            for field in ["question", "answer", "category", "tags", "source", "document_title", "translation_group_id"]
        )
        score = len(terms & _words(text))
        if score:
            scored.append((score, item))
    if not scored:
        return []

    exact = [(score, item) for score, item in scored if normalize_language(item.get("language")) == requested_language]
    fallback = []
    if requested_language != "en":
        fallback = [(score, item) for score, item in scored if normalize_language(item.get("language")) == "en"]
    selected = exact or fallback
    selected.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [
        item
        | {
            "match_score": score,
            "requested_language": requested_language,
            "answer_language": normalize_language(item.get("language")),
            "translated": bool(not exact and requested_language != "en" and normalize_language(item.get("language")) == "en"),
        }
        for score, item in selected[:limit]
    ]


def knowledge_stats(
    conn: sqlite3.Connection,
    business_id: int | None = None,
    workspace_id: int | None = None,
) -> dict[str, int]:
    workspace_id = active_workspace_id(conn, workspace_id)
    where = " where workspace_id = ?"
    args: list[Any] = [workspace_id]
    if business_id:
        where += " and business_id = ?"
        args.append(business_id)
    docs = conn.execute(f"select count(*) from knowledge_documents{where}", args).fetchone()[0]
    item_where = " where businesses.workspace_id = ?"
    item_args: list[Any] = [workspace_id]
    if business_id:
        item_where += " and knowledge_base.business_id = ?"
        item_args.append(business_id)
    items = conn.execute(
        f"""
        select count(*)
        from knowledge_base
        join businesses on businesses.id = knowledge_base.business_id
        {item_where}
        """,
        item_args,
    ).fetchone()[0]
    approved = conn.execute(
        f"""
        select count(*)
        from knowledge_base
        join businesses on businesses.id = knowledge_base.business_id
        {item_where} and coalesce(knowledge_base.status, 'approved') = 'approved'
        """,
        item_args,
    ).fetchone()[0]
    stale = conn.execute(
        f"""
        select count(*) from knowledge_documents
        {where} and julianday('now') - julianday(coalesce(updated_at, created_at)) > ?
        """,
        [*args, STALE_DAYS],
    ).fetchone()[0]
    return {"documents": docs, "items": items, "approved_items": approved, "stale_documents": stale}


def backfill_knowledge_documents(conn: sqlite3.Connection) -> None:
    timestamp = now()
    for business in conn.execute("select id, workspace_id, name from businesses").fetchall():
        existing = conn.execute(
            "select count(*) from knowledge_documents where business_id = ?",
            (business["id"],),
        ).fetchone()[0]
        orphan_count = conn.execute(
            "select count(*) from knowledge_base where business_id = ? and document_id is null",
            (business["id"],),
        ).fetchone()[0]
        if existing or not orphan_count:
            conn.execute(
                """
                update knowledge_base
                set status = coalesce(status, 'approved'),
                    version = coalesce(version, 1),
                    language = coalesce(language, 'en'),
                    approved_at = coalesce(approved_at, created_at, ?),
                    updated_at = coalesce(updated_at, created_at, ?)
                where business_id = ?
                """,
                (timestamp, timestamp, business["id"]),
            )
            continue
        document_id = conn.execute(
            """
            insert into knowledge_documents (
                workspace_id, business_id, title, source_type, source, version, status,
                item_count, approved_by, approved_at, created_at, updated_at
            )
            values (?, ?, ?, 'seed', 'seed_data', 1, 'approved', ?, 'system', ?, ?, ?)
            """,
            (
                business["workspace_id"] or default_workspace_id(conn),
                business["id"],
                f"{business['name']} seed knowledge",
                orphan_count,
                timestamp,
                timestamp,
                timestamp,
            ),
        ).lastrowid
        conn.execute(
            """
            update knowledge_base
            set document_id = ?,
                version = coalesce(version, 1),
                status = coalesce(status, 'approved'),
                language = coalesce(language, 'en'),
                approved_at = coalesce(approved_at, created_at, ?),
                updated_at = coalesce(updated_at, created_at, ?)
            where business_id = ? and document_id is null
            """,
            (document_id, timestamp, timestamp, business["id"]),
        )

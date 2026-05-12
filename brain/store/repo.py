"""CRUD-ish helpers over Neo4j. Used by MCP tools, hooks, and flows.

Plain Cypher; no ORM. Keep functions small and composable.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from brain.store.client import session_scope


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _dumps(val: Any) -> str | None:
    if val is None:
        return None
    return json.dumps(val, default=str)


def _loads(val: Any) -> Any:
    if val in (None, ""):
        return None
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except (ValueError, TypeError):
        return val


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

USER_ID = "singleton"


def user_exists() -> bool:
    with session_scope() as sess:
        rec = sess.run("MATCH (u:User {id: $id}) RETURN u LIMIT 1", id=USER_ID).single()
        return rec is not None


def ensure_user() -> None:
    now = _now()
    with session_scope() as sess:
        sess.run(
            "MERGE (u:User {id: $id}) "
            "ON CREATE SET u.created_at = $now, u.updated_at = $now "
            "ON MATCH SET u.updated_at = $now",
            id=USER_ID,
            now=now,
        )


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


def memory_upsert(
    path: str,
    content: str,
    metadata: dict | None = None,
    source: str = "llm",
) -> dict:
    now = _now()
    meta_json = _dumps(metadata or {})
    with session_scope() as sess:
        rec = sess.run(
            """
            MERGE (m:Memory {path: $path})
            ON CREATE SET m.created_at = $now, m.updated_at = $now,
                          m.content = $content, m.metadata_json = $meta,
                          m.source = $source
            ON MATCH SET m.updated_at = $now, m.content = $content,
                         m.metadata_json = $meta, m.source = $source
            RETURN m.created_at = $now AS created
            """,
            path=path,
            content=content,
            meta=meta_json,
            source=source,
            now=now,
        ).single()
        created = bool(rec["created"]) if rec else False
        # If this memory is a Topic descriptor (path topics/<name>), ensure the
        # Topic node and link.
        if path.startswith("topics/"):
            topic_name = path[len("topics/") :]
            sess.run(
                """
                MERGE (t:Topic {name: $name})
                  ON CREATE SET t.created_at = $now
                WITH t
                MATCH (m:Memory {path: $path})
                MERGE (m)-[:ABOUT]->(t)
                """,
                name=topic_name,
                now=now,
                path=path,
            )
        return {"path": path, "action": "created" if created else "updated"}


def memory_get_by_path(path: str) -> dict | None:
    with session_scope() as sess:
        rec = sess.run(
            "MATCH (m:Memory {path: $path}) "
            "RETURN m.path AS path, m.content AS content, m.metadata_json AS metadata, "
            "       m.source AS source, m.created_at AS created_at, m.updated_at AS updated_at",
            path=path,
        ).single()
        if not rec:
            return None
        return {
            "path": rec["path"],
            "content": rec["content"],
            "metadata": _loads(rec["metadata"]) or {},
            "source": rec["source"],
            "created_at": rec["created_at"],
            "updated_at": rec["updated_at"],
        }


def memory_get_by_prefix(prefix: str, limit: int = 50) -> list[dict]:
    with session_scope() as sess:
        rows = sess.run(
            "MATCH (m:Memory) WHERE m.path STARTS WITH $prefix "
            "RETURN m.path AS path, m.content AS content, m.metadata_json AS metadata, "
            "       m.source AS source, m.updated_at AS updated_at "
            "ORDER BY m.path LIMIT $limit",
            prefix=prefix,
            limit=limit,
        )
        return [
            {
                "path": r["path"],
                "content": r["content"],
                "metadata": _loads(r["metadata"]) or {},
                "source": r["source"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]


def memory_recent(limit: int = 10) -> list[dict]:
    with session_scope() as sess:
        rows = sess.run(
            "MATCH (m:Memory) RETURN m.path AS path, m.content AS content, "
            "m.metadata_json AS metadata, m.source AS source, "
            "m.updated_at AS updated_at "
            "ORDER BY m.updated_at DESC LIMIT $limit",
            limit=limit,
        )
        return [
            {
                "path": r["path"],
                "content": r["content"],
                "metadata": _loads(r["metadata"]) or {},
                "source": r["source"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]


def memory_search(query: str, limit: int = 10) -> list[dict]:
    """Full-text + OR-term fallback."""
    with session_scope() as sess:
        rows = list(
            sess.run(
                "CALL db.index.fulltext.queryNodes('memory_fulltext', $q) "
                "YIELD node, score "
                "RETURN node.path AS path, node.content AS content, "
                "       node.metadata_json AS metadata, node.source AS source, "
                "       node.updated_at AS updated_at, score "
                "ORDER BY score DESC LIMIT $limit",
                q=query,
                limit=limit,
            )
        )
        if not rows:
            terms = [t for t in _terms(query) if len(t) >= 3]
            if terms:
                rows = list(
                    sess.run(
                        "CALL db.index.fulltext.queryNodes('memory_fulltext', $q) "
                        "YIELD node, score "
                        "RETURN node.path AS path, node.content AS content, "
                        "       node.metadata_json AS metadata, node.source AS source, "
                        "       node.updated_at AS updated_at, score "
                        "ORDER BY score DESC LIMIT $limit",
                        q=" OR ".join(terms),
                        limit=limit,
                    )
                )
        return [
            {
                "path": r["path"],
                "content": r["content"],
                "metadata": _loads(r["metadata"]) or {},
                "source": r["source"],
                "updated_at": r["updated_at"],
                "score": r["score"],
            }
            for r in rows
        ]


def _terms(text: str) -> list[str]:
    import re

    return re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", text.lower())


def memory_delete(path: str) -> bool:
    with session_scope() as sess:
        rec = sess.run(
            "MATCH (m:Memory {path: $path}) WITH m, count(m) AS n DETACH DELETE m RETURN n",
            path=path,
        ).single()
        return bool(rec and rec["n"])


def memory_count_by_prefix() -> dict[str, int]:
    """Counts per top-level prefix (profile/, preferences/, topics/, notes/, learned/, ...)."""
    with session_scope() as sess:
        rows = sess.run(
            "MATCH (m:Memory) "
            "WITH split(m.path, '/')[0] AS bucket, count(*) AS n "
            "RETURN bucket, n ORDER BY bucket"
        )
        return {r["bucket"]: r["n"] for r in rows}


def memories_since(iso_timestamp: str, limit: int = 200) -> list[dict]:
    with session_scope() as sess:
        rows = sess.run(
            "MATCH (m:Memory) WHERE m.updated_at >= $since "
            "RETURN m.path AS path, m.content AS content, m.metadata_json AS metadata, "
            "       m.source AS source, m.updated_at AS updated_at "
            "ORDER BY m.updated_at DESC LIMIT $limit",
            since=iso_timestamp,
            limit=limit,
        )
        return [
            {
                "path": r["path"],
                "content": r["content"],
                "metadata": _loads(r["metadata"]) or {},
                "source": r["source"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Sessions / events (read-side; writes happen in hooks/log_event.py)
# ---------------------------------------------------------------------------


def session_get(session_id: str) -> dict | None:
    with session_scope() as sess:
        rec = sess.run(
            "MATCH (s:Session {session_id: $sid}) "
            "RETURN s.session_id AS session_id, s.client AS client, "
            "       s.created_at AS created_at, s.last_event_at AS last_event_at",
            sid=session_id,
        ).single()
        if not rec:
            return None
        return {
            "session_id": rec["session_id"],
            "client": rec["client"],
            "created_at": rec["created_at"],
            "last_event_at": rec["last_event_at"],
        }


def session_events(session_id: str, limit: int = 500) -> list[dict]:
    """Return events for a session in chain order. Empty list if no session."""
    with session_scope() as sess:
        rows = sess.run(
            """
            MATCH (s:Session {session_id: $sid})-[:FIRST_EVENT]->(first:Event)
            MATCH (first)-[:NEXT*0..]->(e:Event)
            RETURN e.event_name AS event_name, e.timestamp AS timestamp,
                   e.prompt AS prompt, e.tool_name AS tool_name,
                   e.tool_input AS tool_input, e.tool_response AS tool_response,
                   e.last_assistant_message AS last_assistant_message
            ORDER BY e.timestamp
            LIMIT $limit
            """,
            sid=session_id,
            limit=limit,
        )
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Plans / Steps
# ---------------------------------------------------------------------------


def plan_create(
    title: str,
    context: str | None = None,
    relates_to_topic: str | None = None,
    steps: list[dict] | None = None,
    session_id: str | None = None,
) -> str:
    plan_id = _new_id("plan")
    now = _now()
    with session_scope() as sess:
        sess.run(
            """
            CREATE (p:Plan {
              id: $id, title: $title, status: 'active',
              context: $context, created_at: $now, updated_at: $now
            })
            """,
            id=plan_id,
            title=title,
            context=context,
            now=now,
        )
        if relates_to_topic:
            sess.run(
                """
                MATCH (p:Plan {id: $pid})
                MERGE (t:Topic {name: $name})
                MERGE (p)-[:RELATES_TO]->(t)
                """,
                pid=plan_id,
                name=relates_to_topic,
            )
        if session_id:
            sess.run(
                """
                MATCH (p:Plan {id: $pid})
                MERGE (s:Session {session_id: $sid})
                MERGE (p)-[:CREATED_IN]->(s)
                """,
                pid=plan_id,
                sid=session_id,
            )
        for i, step in enumerate(steps or []):
            _create_step(sess, plan_id, step.get("text", ""), order=i, status=step.get("status", "pending"))
    return plan_id


def plan_update(
    plan_id: str,
    title: str | None = None,
    status: str | None = None,
    context: str | None = None,
) -> dict:
    now = _now()
    set_clauses = ["p.updated_at = $now"]
    params: dict[str, Any] = {"id": plan_id, "now": now}
    if title is not None:
        set_clauses.append("p.title = $title")
        params["title"] = title
    if status is not None:
        set_clauses.append("p.status = $status")
        params["status"] = status
    if context is not None:
        set_clauses.append("p.context = $context")
        params["context"] = context
    with session_scope() as sess:
        rec = sess.run(
            "MATCH (p:Plan {id: $id}) SET " + ", ".join(set_clauses) + " RETURN p.id AS id",
            **params,
        ).single()
        if not rec:
            raise KeyError(f"plan not found: {plan_id}")
    return {"plan_id": plan_id, "action": "updated"}


def plan_get(plan_id: str) -> dict | None:
    with session_scope() as sess:
        plan = sess.run(
            "MATCH (p:Plan {id: $id}) RETURN p.id AS id, p.title AS title, p.status AS status, "
            "p.context AS context, p.created_at AS created_at, p.updated_at AS updated_at",
            id=plan_id,
        ).single()
        if not plan:
            return None
        steps = list(
            sess.run(
                "MATCH (p:Plan {id: $id})-[r:HAS_STEP]->(s:Step) "
                "RETURN s.id AS id, s.text AS text, s.status AS status, "
                "       s.notes_json AS notes, s.created_at AS created_at, "
                "       s.done_at AS done_at, r.order AS order "
                "ORDER BY r.order",
                id=plan_id,
            )
        )
        topic = sess.run(
            "MATCH (p:Plan {id: $id})-[:RELATES_TO]->(t:Topic) RETURN t.name AS name",
            id=plan_id,
        ).single()
    return {
        "id": plan["id"],
        "title": plan["title"],
        "status": plan["status"],
        "context": plan["context"],
        "created_at": plan["created_at"],
        "updated_at": plan["updated_at"],
        "relates_to_topic": topic["name"] if topic else None,
        "steps": [
            {
                "id": s["id"],
                "text": s["text"],
                "status": s["status"],
                "notes": _loads(s["notes"]) or [],
                "order": s["order"],
                "created_at": s["created_at"],
                "done_at": s["done_at"],
            }
            for s in steps
        ],
    }


def plan_list(status: str | None = "active") -> list[dict]:
    where = "WHERE p.status = $status" if status else ""
    params: dict[str, Any] = {}
    if status:
        params["status"] = status
    with session_scope() as sess:
        plans = list(
            sess.run(
                f"MATCH (p:Plan) {where} "
                "OPTIONAL MATCH (p)-[r:HAS_STEP]->(s:Step) "
                "WITH p, s, r ORDER BY p.updated_at DESC, r.order "
                "WITH p, collect({text: s.text, status: s.status, order: r.order}) AS steps "
                "RETURN p.id AS id, p.title AS title, p.status AS status, steps",
                **params,
            )
        )
    out = []
    for row in plans:
        next_step = next(
            (s["text"] for s in row["steps"] if s["status"] == "pending"),
            None,
        )
        out.append(
            {
                "id": row["id"],
                "title": row["title"],
                "status": row["status"],
                "next_step": next_step,
                "step_count": len([s for s in row["steps"] if s["text"]]),
            }
        )
    return out


def _create_step(sess, plan_id: str, text: str, *, order: int | None = None, status: str = "pending") -> str:
    step_id = _new_id("step")
    now = _now()
    if order is None:
        rec = sess.run(
            "MATCH (:Plan {id: $pid})-[r:HAS_STEP]->() RETURN coalesce(max(r.order), -1) AS m",
            pid=plan_id,
        ).single()
        order = (rec["m"] if rec else -1) + 1
    sess.run(
        """
        MATCH (p:Plan {id: $pid})
        CREATE (s:Step {
          id: $id, text: $text, status: $status,
          notes_json: '[]', created_at: $now
        })
        CREATE (p)-[:HAS_STEP {order: $order}]->(s)
        """,
        pid=plan_id,
        id=step_id,
        text=text,
        status=status,
        now=now,
        order=order,
    )
    return step_id


def step_create(plan_id: str, text: str, after_step_id: str | None = None) -> str:
    with session_scope() as sess:
        if after_step_id:
            rec = sess.run(
                "MATCH (:Plan {id: $pid})-[r:HAS_STEP]->(s:Step {id: $sid}) RETURN r.order AS o",
                pid=plan_id,
                sid=after_step_id,
            ).single()
            if rec is None:
                raise KeyError(f"after_step_id not found in plan: {after_step_id}")
            insert_order = rec["o"] + 1
            sess.run(
                "MATCH (:Plan {id: $pid})-[r:HAS_STEP]->() WHERE r.order >= $o SET r.order = r.order + 1",
                pid=plan_id,
                o=insert_order,
            )
            return _create_step(sess, plan_id, text, order=insert_order)
        return _create_step(sess, plan_id, text)


def step_update(
    plan_id: str,
    step_id: str,
    text: str | None = None,
    status: str | None = None,
    note: str | None = None,
) -> dict:
    now = _now()
    set_clauses: list[str] = []
    params: dict[str, Any] = {"sid": step_id}
    if text is not None:
        set_clauses.append("s.text = $text")
        params["text"] = text
    if status is not None:
        set_clauses.append("s.status = $status")
        params["status"] = status
        if status == "done":
            set_clauses.append("s.done_at = $now")
            params["now"] = now
    with session_scope() as sess:
        if set_clauses:
            rec = sess.run(
                "MATCH (s:Step {id: $sid}) SET " + ", ".join(set_clauses) + " RETURN s.id AS id",
                **params,
            ).single()
            if not rec:
                raise KeyError(f"step not found: {step_id}")
        if note:
            _append_note(sess, step_id, note, now)
        if plan_id:
            sess.run(
                "MATCH (p:Plan {id: $pid}) SET p.updated_at = $now",
                pid=plan_id,
                now=now,
            )
    return {"step_id": step_id, "action": "updated"}


def _append_note(sess, step_id: str, note: str, now: str) -> None:
    # Append without APOC: read JSON in Python, write back.
    rec = sess.run(
        "MATCH (s:Step {id: $sid}) RETURN coalesce(s.notes_json, '[]') AS j",
        sid=step_id,
    ).single()
    if not rec:
        raise KeyError(f"step not found: {step_id}")
    notes = _loads(rec["j"]) or []
    notes.append({"at": now, "text": note})
    sess.run(
        "MATCH (s:Step {id: $sid}) SET s.notes_json = $j",
        sid=step_id,
        j=_dumps(notes),
    )


# ---------------------------------------------------------------------------
# Flows / Fires
# ---------------------------------------------------------------------------


def flow_ensure(flow_id: str) -> None:
    now = _now()
    with session_scope() as sess:
        sess.run(
            """
            MERGE (f:Flow {id: $id})
              ON CREATE SET f.fires = 0, f.surfaced = 0,
                            f.positive_feedback = 0, f.negative_feedback = 0,
                            f.created_at = $now
            """,
            id=flow_id,
            now=now,
        )


def fire_record(flow_id: str) -> str:
    """Mark a fire in progress. Returns fire_id; call fire_finish to complete."""
    fire_id = _new_id("fire")
    now = _now()
    flow_ensure(flow_id)
    with session_scope() as sess:
        sess.run(
            """
            MATCH (f:Flow {id: $fid})
            CREATE (fi:Fire {
              id: $id, at: $now, succeeded: null, memories_written: 0
            })
            CREATE (f)-[:FIRED]->(fi)
            SET f.fires = coalesce(f.fires, 0) + 1, f.last_fired_at = $now
            """,
            fid=flow_id,
            id=fire_id,
            now=now,
        )
    return fire_id


def fire_finish(
    fire_id: str,
    *,
    succeeded: bool,
    error: str | None = None,
    memory_paths: list[str] | None = None,
) -> None:
    paths = memory_paths or []
    with session_scope() as sess:
        sess.run(
            "MATCH (fi:Fire {id: $id}) SET fi.succeeded = $ok, fi.error = $err, "
            "fi.memories_written = $n",
            id=fire_id,
            ok=succeeded,
            err=error,
            n=len(paths),
        )
        for p in paths:
            sess.run(
                "MATCH (fi:Fire {id: $id}), (m:Memory {path: $p}) "
                "MERGE (fi)-[:PRODUCED]->(m)",
                id=fire_id,
                p=p,
            )


def recent_fires(limit: int = 10) -> list[dict]:
    with session_scope() as sess:
        rows = sess.run(
            """
            MATCH (f:Flow)-[:FIRED]->(fi:Fire)
            RETURN f.id AS flow_id, fi.at AS at, fi.succeeded AS ok,
                   fi.error AS error, fi.memories_written AS n
            ORDER BY fi.at DESC LIMIT $limit
            """,
            limit=limit,
        )
        return [
            {
                "flow_id": r["flow_id"],
                "at": r["at"],
                "succeeded": r["ok"],
                "error": r["error"],
                "memories_written": r["n"],
            }
            for r in rows
        ]


def flow_stats() -> list[dict]:
    with session_scope() as sess:
        rows = sess.run(
            "MATCH (f:Flow) RETURN f.id AS id, f.fires AS fires, "
            "f.surfaced AS surfaced, f.last_fired_at AS last_fired_at "
            "ORDER BY f.last_fired_at DESC"
        )
        return [
            {
                "id": r["id"],
                "fires": r["fires"] or 0,
                "surfaced": r["surfaced"] or 0,
                "last_fired_at": r["last_fired_at"],
            }
            for r in rows
        ]

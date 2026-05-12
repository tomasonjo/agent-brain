"""Append every harness event to Neo4j as an :Event in a per-session chain.

Schema:
    (Session)-[:FIRST_EVENT]->(Event)
    (Session)-[:LATEST_EVENT]->(Event)
    (Event)-[:NEXT]->(Event)

Adapted from tomasonjo/agent-memory-hooks-neo4j.

Silent on success. Errors go to stderr; always exits 0.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime

from brain.config import SETTINGS
from brain.hooks.common import read_payload
from brain.store.client import session_scope

MAX_RESPONSE_CHARS = 4000


def _serialize_tool_response(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    if len(text) > MAX_RESPONSE_CHARS:
        text = text[:MAX_RESPONSE_CHARS] + f"...[truncated {len(text) - MAX_RESPONSE_CHARS} chars]"
    return text


def _read_transcript(path: str | None) -> str | None:
    if not path:
        return None
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def _build_event_props(data: dict, client: str, event_id: str, timestamp: str) -> dict:
    props = {
        "event_id": event_id,
        "event_name": data.get("hook_event_name", "unknown"),
        "client": client,
        "timestamp": timestamp,
        "cwd": data.get("cwd"),
        "tool_name": data.get("tool_name"),
        "tool_use_id": data.get("tool_use_id"),
        "tool_input": json.dumps(data.get("tool_input")) if data.get("tool_input") else None,
        "tool_response": _serialize_tool_response(data.get("tool_response"))
        if data.get("tool_response") is not None
        else None,
        "prompt": data.get("prompt"),
        "model": data.get("model"),
        "source": data.get("source"),
        "turn_id": data.get("turn_id"),
        "last_assistant_message": data.get("last_assistant_message"),
        "stop_hook_active": data.get("stop_hook_active"),
        "transcript_path": data.get("transcript_path"),
        "transcript": _read_transcript(data.get("transcript_path")),
    }
    return {k: v for k, v in props.items() if v is not None}


def _append_event(tx, session_id: str, client: str, event_props: dict) -> None:
    tx.run(
        """
        MERGE (s:Session {session_id: $session_id})
          ON CREATE SET s.created_at = $timestamp, s.client = $client
        SET s.client = coalesce(s.client, $client),
            s.last_event_at = $timestamp
        WITH s
        CREATE (e:Event $event_props)
        WITH s, e
        OPTIONAL MATCH (s)-[old_latest:LATEST_EVENT]->(prev:Event)
        DELETE old_latest
        WITH s, e, prev
        FOREACH (_ IN CASE WHEN prev IS NOT NULL THEN [1] ELSE [] END |
            CREATE (prev)-[:NEXT]->(e)
        )
        FOREACH (_ IN CASE WHEN prev IS NULL THEN [1] ELSE [] END |
            CREATE (s)-[:FIRST_EVENT]->(e)
        )
        CREATE (s)-[:LATEST_EVENT]->(e)
        """,
        session_id=session_id,
        client=client,
        timestamp=event_props.get("timestamp"),
        event_props=event_props,
    )


def _spawn_session_dream(session_id: str | None) -> None:
    """Kick off dream_session for the just-ended session, detached.

    Returns immediately; the dream runs in its own process group so harness
    exit doesn't kill it. Disable via BRAIN_DREAM_ON_STOP=0.
    """
    if not session_id:
        return
    if os.environ.get("BRAIN_DREAM_ON_STOP", "1").lower() in ("0", "false", "no"):
        return
    try:
        subprocess.Popen(
            [sys.executable, "-m", "brain.cli.brain", "dream", session_id],
            cwd=str(SETTINGS.repo_root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception as e:
        print(f"failed to spawn dream: {e}", file=sys.stderr)


def log_event(data: dict, client: str) -> None:
    session_id = data.get("session_id", "unknown")
    event_name = data.get("hook_event_name", "unknown")
    timestamp = datetime.now(UTC).isoformat()
    event_id = f"{client}_{session_id}_{timestamp}_{event_name}"
    props = _build_event_props(data, client, event_id, timestamp)
    with session_scope() as sess:
        sess.execute_write(_append_event, session_id, client, props)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True, choices=["claude_code", "codex", "cursor"])
    args = parser.parse_args()
    try:
        data = read_payload()
        log_event(data, client=args.client)
        if (data.get("hook_event_name") or "").lower() == "stop":
            _spawn_session_dream(data.get("session_id"))
    except Exception as e:  # never crash the harness
        print(f"log_event error: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

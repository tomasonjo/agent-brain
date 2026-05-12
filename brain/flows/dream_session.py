"""Session-end memory distillation.

Reads one session's :Event chain, asks the LLM to extract any durable memories
the agent didn't already save during the conversation, and writes them.

params:
    session_id: str (required)

Output: list of memory paths written.
"""

from __future__ import annotations

import logging
import os
import time

from anthropic import Anthropic

from brain.config import SETTINGS
from brain.flows._dream_common import format_session_transcript, parse_json_array, valid_path
from brain.store import repo

log = logging.getLogger("brain.flows.dream_session")

DEFAULT_DEBOUNCE_SECONDS = int(os.environ.get("BRAIN_DREAM_DEBOUNCE_SECONDS", "60"))


def _debounce_ok(session_id: str, seconds: int) -> bool:
    """File-lock debounce. Returns True iff dream should proceed for this session."""
    lock_dir = SETTINGS.repo_root / ".brain" / "dream_locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock = lock_dir / f"{session_id}.lock"
    now = time.time()
    if lock.exists() and (now - lock.stat().st_mtime) < seconds:
        return False
    lock.touch()
    return True

SYSTEM_PROMPT = """You distill durable memories from one session of conversation
between a user and their personal agent. Your job: extract things worth remembering
that were NOT already saved.

SAVE:
- Stable facts about the user (role, location, what they own, who's in their life).
- Preferences and working styles ("user prefers concise responses", "uses zsh").
- Lasting decisions or commitments ("decided to use Postgres", "wants to learn Go").
- Project context they'll want next session.

SKIP:
- Commands run, code edits, intermediate confusion.
- Things already in the "Already saved" list.
- One-off questions with no lasting signal.

Output a JSON array. Each item: {path, content, metadata?}.
Paths must be lowercase, slash-separated, match ^[a-z][a-z0-9_-]*(/[a-z0-9._-]+)+$.
Use prefixes: profile/, preferences/, learned/, projects/. Avoid notes/ (that's for
daily flow output).

If nothing memory-worthy, output [].
Output ONLY the JSON array, no prose."""


def _build_user_message(transcript: str, already_saved: list[dict]) -> str:
    if already_saved:
        listing = "\n".join(
            f"- {m['path']}: {(m.get('content') or '')[:120]}" for m in already_saved
        )
    else:
        listing = "(none)"
    return (
        f"# Already saved (skip these)\n{listing}\n\n"
        f"# Session transcript\n{transcript}\n\n"
        "Extract new durable memories. JSON array only."
    )


def run(params: dict, *, fire_id: str) -> list[str]:
    session_id = params.get("session_id")
    if not session_id:
        raise ValueError("dream_session requires params.session_id")

    debounce = int(params.get("debounce_seconds", DEFAULT_DEBOUNCE_SECONDS))
    if debounce > 0 and not _debounce_ok(session_id, debounce):
        log.info("dream_session %s: debounced (within %ds)", session_id, debounce)
        return []

    events = repo.session_events(session_id)
    if not events:
        log.info("session %s has no events; nothing to dream", session_id)
        return []

    transcript = format_session_transcript(events)
    if not transcript:
        log.info("session %s transcript empty after filtering; skipping", session_id)
        return []

    already = repo.memory_recent(limit=40)

    client = Anthropic(api_key=SETTINGS.anthropic_api_key)
    resp = client.messages.create(
        model=SETTINGS.model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_message(transcript, already)}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()

    extracted = parse_json_array(text)
    if not extracted:
        log.info("session %s dream: nothing extracted", session_id)
        return []

    written: list[str] = []
    for item in extracted:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        content = item.get("content")
        if not valid_path(path) or not content:
            log.warning("dream skipped invalid item: %r", item)
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        metadata = {**metadata, "dreamed_from_session": session_id}
        try:
            repo.memory_upsert(
                path,
                content,
                metadata=metadata,
                source=f"dream:{session_id}",
            )
            written.append(path)
        except Exception:
            log.exception("dream failed to write %s", path)
    log.info("session %s dream wrote %d memories", session_id, len(written))
    return written

"""Cross-session synthesis. Optional cron-driven.

Looks at recent memories, identifies 1-3 themes worth a synthesized note,
writes them under synthesis/<slug>.

params:
    days: int          look back this many days (default 7)
    max_memories: int  cap input size (default 100)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from anthropic import Anthropic

from brain.config import SETTINGS
from brain.flows._dream_common import parse_json_array, valid_path
from brain.store import repo

log = logging.getLogger("brain.flows.dream_synthesis")

SYSTEM_PROMPT = """You synthesize patterns from a personal agent's recent memories.

Read the list of memories below. Identify 1-3 themes that recur or that, taken
together, paint a higher-level picture worth a standalone note.

Examples of good themes:
- "User has been ramping on Rust over the last week"
- "Recurring frustration with build flakes"
- "Shifting interest from AI infra toward applied product work"

Examples of bad themes:
- Anything obvious from one memory alone.
- Restating individual facts.

Output JSON array. Each item: {path, content}.
Paths must start with synthesis/ and end with a slug, e.g. synthesis/rust-ramp,
synthesis/2026-w19-themes. Match ^[a-z][a-z0-9_-]*(/[a-z0-9._-]+)+$.

If no real themes emerge, output [].
Output ONLY the JSON array."""


def _format_memories(mems: list[dict]) -> str:
    parts: list[str] = []
    for m in mems:
        snippet = (m.get("content") or "").strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "..."
        parts.append(f"## {m['path']} ({m.get('updated_at')})\n{snippet}")
    return "\n\n".join(parts)


def run(params: dict, *, fire_id: str) -> list[str]:
    days = int(params.get("days", 7))
    max_memories = int(params.get("max_memories", 100))
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    mems = repo.memories_since(cutoff, limit=max_memories)
    if len(mems) < 3:
        log.info("dream_synthesis: only %d memories since %s; skipping", len(mems), cutoff)
        return []

    listing = _format_memories(mems)
    client = Anthropic(api_key=SETTINGS.anthropic_api_key)
    resp = client.messages.create(
        model=SETTINGS.model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Memories from the past {days} days:\n\n{listing}\n\nSynthesize.",
            }
        ],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()

    extracted = parse_json_array(text)
    if not extracted:
        return []

    written: list[str] = []
    for item in extracted:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        content = item.get("content")
        if not valid_path(path) or not path.startswith("synthesis/") or not content:
            log.warning("dream_synthesis skipped invalid item: %r", item)
            continue
        try:
            repo.memory_upsert(
                path,
                content,
                metadata={"window_days": days, "memory_count": len(mems)},
                source="dream:synthesis",
            )
            written.append(path)
        except Exception:
            log.exception("dream_synthesis failed to write %s", path)
    log.info("dream_synthesis wrote %d memories", len(written))
    return written

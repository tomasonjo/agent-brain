"""Shared helpers for dream flows: JSON parsing, transcript formatting."""

from __future__ import annotations

import json
import re

from brain.mcp_server.validation import MEMORY_PATH_RE


def parse_json_array(text: str) -> list[dict]:
    """Extract a JSON array from LLM output. Tolerates ```json``` fences and trailing prose."""
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    # Try the whole thing first
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, ValueError):
        pass
    # Find the first top-level [ ... ] span
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, ValueError):
        return []


def format_session_transcript(events: list[dict], *, max_chars: int = 20_000) -> str:
    """Strip events down to user prompts + final assistant messages. Tool calls excluded."""
    lines: list[str] = []
    for e in events:
        evt = (e.get("event_name") or "").lower().replace("_", "")
        if evt in {"userpromptsubmit", "beforesubmitprompt"} and e.get("prompt"):
            lines.append(f"USER: {e['prompt']}")
        elif evt == "stop" and e.get("last_assistant_message"):
            lines.append(f"ASSISTANT: {e['last_assistant_message']}")
    out = "\n\n".join(lines)
    if len(out) > max_chars:
        out = out[:max_chars] + "\n\n...[truncated]"
    return out


def valid_path(path: str | None) -> bool:
    return bool(path) and MEMORY_PATH_RE.match(path or "") is not None

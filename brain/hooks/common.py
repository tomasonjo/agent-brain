"""Shared utilities for hook entry points.

Hooks must never crash the harness. Every entry point in this package wraps
its body in a try/except and exits 0 regardless. Errors go to stderr.
"""

from __future__ import annotations

import json
import sys


def read_payload() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}


def emit_additional_context(event_name: str, context: str) -> None:
    """Write hookSpecificOutput JSON that both Claude Code and Codex understand."""
    if not context.strip():
        return
    out = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": context,
        }
    }
    sys.stdout.write(json.dumps(out))
    sys.stdout.write("\n")
    sys.stdout.flush()


def normalize_event_name(event: str | None) -> str:
    """Map per-client event names to a canonical lowercased form."""
    e = (event or "").lower().replace("_", "")
    aliases = {
        "sessionstart": "sessionstart",
        "userpromptsubmit": "userpromptsubmit",
        "beforesubmitprompt": "userpromptsubmit",
        "pretooluse": "pretooluse",
        "posttooluse": "posttooluse",
        "stop": "stop",
    }
    return aliases.get(e, e)

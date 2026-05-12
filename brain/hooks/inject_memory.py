"""Inject memory/onboarding context at SessionStart and UserPromptSubmit.

SessionStart:
    Empty DB (no :User) → emit prompts/onboarding.md so the LLM walks the
    user through profile + interests + scheduled flows.
    Populated DB → emit profile/preferences memories, active plans,
    recent flow-produced memories, and recent fires.

UserPromptSubmit:
    Full-text search across :Memory; OR-term fallback if no hits.

Errors go to stderr; always exits 0.
"""

from __future__ import annotations

import argparse
import sys

from brain.config import SETTINGS
from brain.hooks.common import emit_additional_context, normalize_event_name, read_payload
from brain.store import repo

PROMPTS_DIR = SETTINGS.repo_root / "prompts"


def _load_onboarding_prompt() -> str:
    path = PROMPTS_DIR / "onboarding.md"
    try:
        return path.read_text()
    except OSError:
        return ""


def _format_memory_block(title: str, mems: list[dict]) -> str:
    if not mems:
        return ""
    lines = [f"## {title}\n"]
    for m in mems:
        lines.append(f"### {m['path']}\n{m['content']}\n")
    return "\n".join(lines)


def _format_plans(plans: list[dict]) -> str:
    if not plans:
        return ""
    lines = ["## Active plans\n"]
    for p in plans:
        next_part = f" — next: {p['next_step']}" if p.get("next_step") else ""
        lines.append(f"- **{p['title']}** (`{p['id']}`, {p['step_count']} steps){next_part}")
    return "\n".join(lines) + "\n"


def _format_fires(fires: list[dict]) -> str:
    if not fires:
        return ""
    lines = ["## Recent flow runs\n"]
    for f in fires[:5]:
        status = "ok" if f.get("succeeded") else ("failed" if f.get("succeeded") is False else "running")
        lines.append(f"- `{f['flow_id']}` @ {f['at']} — {status}, {f['memories_written']} memories")
    return "\n".join(lines) + "\n"


def _format_recent_memories(mems: list[dict]) -> str:
    if not mems:
        return ""
    lines = ["## Recent memories\n"]
    for m in mems:
        snippet = (m["content"] or "").strip().splitlines()[0] if m.get("content") else ""
        if len(snippet) > 140:
            snippet = snippet[:137] + "..."
        lines.append(f"- `{m['path']}` — {snippet}")
    return "\n".join(lines) + "\n"


def session_start_context() -> str:
    if not repo.user_exists():
        prompt = _load_onboarding_prompt()
        if not prompt:
            return "# Onboarding\n\nThe agent-brain DB is empty. Please onboard the user."
        return prompt

    parts: list[str] = ["# Brain memory (prior sessions)\n"]
    profile = repo.memory_get_by_prefix("profile/", limit=10)
    if profile:
        parts.append(_format_memory_block("Profile", profile))
    prefs = repo.memory_get_by_prefix("preferences/", limit=10)
    if prefs:
        parts.append(_format_memory_block("Preferences", prefs))
    topics = repo.memory_get_by_prefix("topics/", limit=20)
    if topics:
        parts.append(_format_memory_block("Topics", topics))
    plans_block = _format_plans(repo.plan_list("active"))
    if plans_block:
        parts.append(plans_block)
    recent_mem_block = _format_recent_memories(repo.memory_recent(5))
    if recent_mem_block:
        parts.append(recent_mem_block)
    fires_block = _format_fires(repo.recent_fires(5))
    if fires_block:
        parts.append(fires_block)
    return "\n".join(parts)


def prompt_context(prompt: str) -> str:
    if not prompt.strip():
        return ""
    hits = repo.memory_search(prompt, limit=5)
    if not hits:
        return ""
    parts = ["# Relevant memory for this prompt\n"]
    for h in hits:
        parts.append(f"## {h['path']}\n{h['content']}\n")
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True, choices=["claude_code", "codex", "cursor"])
    parser.parse_args()
    try:
        data = read_payload()
        event = data.get("hook_event_name")
        canonical = normalize_event_name(event)
        if canonical == "sessionstart":
            emit_additional_context(event or "SessionStart", session_start_context())
        elif canonical == "userpromptsubmit":
            emit_additional_context(event or "UserPromptSubmit", prompt_context(data.get("prompt", "")))
    except Exception as e:
        print(f"inject_memory error: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

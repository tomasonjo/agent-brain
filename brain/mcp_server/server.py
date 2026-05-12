"""FastMCP server. Ten tools cover memory + triggers + plans + system state.

Run:
    python -m brain.mcp_server.server
"""

from __future__ import annotations

from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP

from brain.config import SETTINGS
from brain.flows import FLOWS
from brain.mcp_server.validation import (
    VALID_PLAN_STATUS,
    VALID_STEP_STATUS,
    validate_memory_path,
    validate_trigger_config,
    validate_trigger_id,
)
from brain.store import repo

mcp = FastMCP("agent-brain")


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


@mcp.tool()
def memory_upsert(path: str, content: str, metadata: dict | None = None) -> dict:
    """Create or replace a Memory at `path`.

    Path conventions (the skill explains in detail):
      - profile/<key>       : user identity (role, name, location)
      - preferences/<key>   : how the user wants to be helped
      - topics/<slug>       : an interest area; metadata may include
                              diffbot_category and diffbot_text_filter
      - notes/<YYYY-MM-DD>-<slug> : journal entries
      - learned/<slug>      : durable facts about the user's world

    Path must match ^[a-z][a-z0-9_-]*(/[a-z0-9._-]+)+$.
    Returns: {path, action: "created" | "updated"}
    """
    validate_memory_path(path)
    return repo.memory_upsert(path, content, metadata or {}, source="llm")


@mcp.tool()
def memory_get(
    path: str | None = None,
    query: str | None = None,
    prefix: str | None = None,
    recent_n: int | None = None,
) -> list[dict]:
    """Read memories. Provide exactly one of: path, query, prefix, recent_n.

    - path: exact match for a single memory (returns 0 or 1 result)
    - query: full-text search across content + path
    - prefix: list memories whose path starts with prefix (e.g. "topics/")
    - recent_n: N most recently updated memories
    """
    provided = sum(1 for x in (path, query, prefix, recent_n) if x is not None)
    if provided != 1:
        raise ValueError("provide exactly one of: path, query, prefix, recent_n")
    if path is not None:
        mem = repo.memory_get_by_path(path)
        return [mem] if mem else []
    if query is not None:
        return repo.memory_search(query, limit=10)
    if prefix is not None:
        return repo.memory_get_by_prefix(prefix, limit=50)
    return repo.memory_recent(limit=int(recent_n))


@mcp.tool()
def memory_delete(path: str) -> dict:
    """Delete the Memory at path. Returns {deleted: bool}."""
    validate_memory_path(path)
    return {"deleted": repo.memory_delete(path)}


# ---------------------------------------------------------------------------
# Triggers (write the local YAML, no git)
# ---------------------------------------------------------------------------


def _trigger_path(trigger_id: str):
    SETTINGS.triggers_dir.mkdir(parents=True, exist_ok=True)
    return SETTINGS.triggers_dir / f"{trigger_id}.yaml"


def _read_trigger_file(trigger_id: str) -> dict | None:
    p = _trigger_path(trigger_id)
    if not p.exists():
        return None
    return yaml.safe_load(p.read_text()) or {}


def _active_trigger_count(exclude: str | None = None) -> int:
    count = 0
    if not SETTINGS.triggers_dir.exists():
        return 0
    for f in SETTINGS.triggers_dir.glob("*.yaml"):
        if exclude and f.stem == exclude:
            continue
        try:
            cfg = yaml.safe_load(f.read_text()) or {}
        except yaml.YAMLError:
            continue
        if cfg.get("status", "active") == "active":
            count += 1
    return count


@mcp.tool()
def trigger_upsert(id: str, config: dict) -> dict:
    """Create or update a trigger. Writes triggers/<id>.yaml.

    config shape:
      {
        "flow": "daily_brief",
        "schedule": {"type": "cron", "expr": "0 7 * * 1-5", "tz": "Europe/Ljubljana"},
        "params": {"topic_path": "topics/ai", "max_articles": 10},
        "status": "active",    # active | paused | dormant
        "pinned": false,
        "description": "..."
      }

    Validation: cron parses; flow exists; active count <= BRAIN_MAX_ACTIVE_TRIGGERS;
    refuses to overwrite a pinned trigger unless the new config is also pinned.
    """
    validate_trigger_id(id)
    normalized = validate_trigger_config(config, known_flows=set(FLOWS.keys()))

    existing = _read_trigger_file(id)
    if existing and existing.get("pinned") and not normalized["pinned"]:
        raise ValueError(
            f"trigger {id!r} is pinned; new config must also have pinned: true"
        )

    if normalized["status"] == "active":
        count = _active_trigger_count(exclude=id)
        if count + 1 > SETTINGS.max_active_triggers:
            raise ValueError(
                f"cannot exceed BRAIN_MAX_ACTIVE_TRIGGERS ({SETTINGS.max_active_triggers}); "
                f"currently {count} active. Pause or delete one first."
            )

    payload = {"id": id, **normalized}
    path = _trigger_path(id)
    action = "updated" if path.exists() else "created"
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    repo.flow_ensure(id)
    return {"id": id, "action": action, "path": str(path.relative_to(SETTINGS.repo_root))}


@mcp.tool()
def trigger_list(status: str | None = None) -> list[dict]:
    """List triggers. Filter by status (active|paused|dormant) or omit for all.

    Each entry merges the YAML config with stats from Neo4j (fires, last_fired_at).
    """
    if not SETTINGS.triggers_dir.exists():
        return []
    stats_by_id = {s["id"]: s for s in repo.flow_stats()}
    out: list[dict] = []
    for f in sorted(SETTINGS.triggers_dir.glob("*.yaml")):
        try:
            cfg = yaml.safe_load(f.read_text()) or {}
        except yaml.YAMLError:
            continue
        if status and cfg.get("status") != status:
            continue
        stats = stats_by_id.get(cfg.get("id"), {})
        cfg["stats"] = {
            "fires": stats.get("fires", 0),
            "surfaced": stats.get("surfaced", 0),
            "last_fired_at": stats.get("last_fired_at"),
        }
        out.append(cfg)
    return out


@mcp.tool()
def trigger_delete(id: str) -> dict:
    """Delete a trigger. Refuses if pinned. Returns {deleted: bool}."""
    validate_trigger_id(id)
    cfg = _read_trigger_file(id)
    if not cfg:
        return {"deleted": False}
    if cfg.get("pinned"):
        raise ValueError(f"trigger {id!r} is pinned; unpin via trigger_upsert first")
    _trigger_path(id).unlink()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


@mcp.tool()
def plan_upsert(
    plan_id: str | None = None,
    title: str | None = None,
    status: str | None = None,
    context: str | None = None,
    relates_to_topic: str | None = None,
    steps: list[dict] | None = None,
) -> dict:
    """Create or update a plan.

    - Without plan_id: creates a new plan. title required. steps optional bulk init.
      Each step is {"text": "...", "status": "pending"} (status optional).
    - With plan_id: updates given fields. steps are ignored on update.

    status: one of active | paused | done | abandoned.
    """
    if status is not None and status not in VALID_PLAN_STATUS:
        raise ValueError(f"status must be one of {sorted(VALID_PLAN_STATUS)}")
    if plan_id is None:
        if not title:
            raise ValueError("title required when creating a plan")
        new_id = repo.plan_create(
            title=title,
            context=context,
            relates_to_topic=relates_to_topic,
            steps=steps or [],
        )
        return {"plan_id": new_id, "action": "created"}
    return repo.plan_update(plan_id, title=title, status=status, context=context)


@mcp.tool()
def plan_get(plan_id: str | None = None) -> Any:
    """Without plan_id: list active plans (id, title, next pending step).
    With plan_id: full plan with all steps and per-step iteration notes.
    """
    if plan_id is None:
        return repo.plan_list("active")
    plan = repo.plan_get(plan_id)
    if not plan:
        raise KeyError(f"plan not found: {plan_id}")
    return plan


@mcp.tool()
def step_upsert(
    plan_id: str,
    step_id: str | None = None,
    text: str | None = None,
    status: str | None = None,
    after_step_id: str | None = None,
    note: str | None = None,
) -> dict:
    """Create or update a step.

    - Without step_id: creates a step. text required. after_step_id inserts
      after a given step (otherwise appended at the end).
    - With step_id: updates given fields. Combine status="done" with note="..."
      to mark done and log what happened in one call.
    - note always appends to the iteration log; never replaces.

    status: pending | in_progress | done | skipped.
    """
    if status is not None and status not in VALID_STEP_STATUS:
        raise ValueError(f"status must be one of {sorted(VALID_STEP_STATUS)}")
    if step_id is None:
        if not text:
            raise ValueError("text required when creating a step")
        new_id = repo.step_create(plan_id, text, after_step_id=after_step_id)
        if status or note:
            repo.step_update(plan_id, new_id, status=status, note=note)
        return {"step_id": new_id, "action": "created"}
    return repo.step_update(plan_id, step_id, text=text, status=status, note=note)


# ---------------------------------------------------------------------------
# System state
# ---------------------------------------------------------------------------


@mcp.tool()
def system_state() -> dict:
    """Snapshot of brain state: user, active triggers, recent fires,
    active plans, memory counts, and recent memories.
    """
    return {
        "user_exists": repo.user_exists(),
        "active_triggers": trigger_list(status="active"),
        "recent_fires": repo.recent_fires(limit=10),
        "active_plans": repo.plan_list("active"),
        "memory_counts": repo.memory_count_by_prefix(),
        "recent_memories": [
            {"path": m["path"], "updated_at": m["updated_at"]}
            for m in repo.memory_recent(limit=10)
        ],
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

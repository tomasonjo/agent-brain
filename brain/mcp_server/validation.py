"""Validation for memory paths, trigger configs, and trigger IDs."""

from __future__ import annotations

import re
from typing import Any

from croniter import croniter

MEMORY_PATH_RE = re.compile(r"^[a-z][a-z0-9_-]*(/[a-z0-9._-]+)+$")
TRIGGER_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

VALID_TRIGGER_STATUS = {"active", "paused", "dormant"}
VALID_PLAN_STATUS = {"active", "paused", "done", "abandoned"}
VALID_STEP_STATUS = {"pending", "in_progress", "done", "skipped"}


def validate_memory_path(path: str) -> None:
    if not MEMORY_PATH_RE.match(path):
        raise ValueError(
            f"invalid memory path: {path!r}. "
            "Use lowercase segments separated by /, e.g. profile/role, topics/ai, "
            "notes/2026-05-12-foo"
        )


def validate_trigger_id(trigger_id: str) -> None:
    if not TRIGGER_ID_RE.match(trigger_id):
        raise ValueError(
            f"invalid trigger id: {trigger_id!r}. Use [a-z][a-z0-9_]*"
        )


def validate_trigger_config(config: dict, *, known_flows: set[str]) -> dict:
    """Returns a normalized config dict. Raises ValueError on problems."""
    if not isinstance(config, dict):
        raise ValueError("trigger config must be an object")

    out: dict[str, Any] = {}
    out["flow"] = _require(config, "flow", str)
    if out["flow"] not in known_flows:
        raise ValueError(
            f"unknown flow {out['flow']!r}. Known flows: {sorted(known_flows)}"
        )

    sched = _require(config, "schedule", dict)
    if sched.get("type") != "cron":
        raise ValueError("schedule.type must be 'cron' for now")
    expr = _require(sched, "expr", str)
    if not croniter.is_valid(expr):
        raise ValueError(f"invalid cron expression: {expr!r}")
    out["schedule"] = {
        "type": "cron",
        "expr": expr,
        "tz": sched.get("tz") or "UTC",
    }

    params = config.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    out["params"] = params

    status = config.get("status", "active")
    if status not in VALID_TRIGGER_STATUS:
        raise ValueError(f"status must be one of {sorted(VALID_TRIGGER_STATUS)}")
    out["status"] = status

    out["pinned"] = bool(config.get("pinned", False))
    out["description"] = config.get("description") or ""
    return out


def _require(obj: dict, key: str, expected_type: type) -> Any:
    if key not in obj:
        raise ValueError(f"missing required field: {key}")
    val = obj[key]
    if not isinstance(val, expected_type):
        raise ValueError(f"{key} must be {expected_type.__name__}")
    return val

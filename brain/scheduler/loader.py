"""Read trigger YAML files from disk."""

from __future__ import annotations

from pathlib import Path

import yaml

from brain.config import SETTINGS


def load_one(path: Path) -> dict | None:
    try:
        cfg = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return None
    if not cfg.get("id"):
        cfg["id"] = path.stem
    return cfg


def load_all() -> list[dict]:
    out: list[dict] = []
    if not SETTINGS.triggers_dir.exists():
        return out
    for f in sorted(SETTINGS.triggers_dir.glob("*.yaml")):
        cfg = load_one(f)
        if cfg:
            out.append(cfg)
    return out

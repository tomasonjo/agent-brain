"""Centralized env-derived settings. Imported by every entry point."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


load_dotenv(_repo_root() / ".env", override=False)


def _env(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str
    diffbot_api_key: str | None
    anthropic_api_key: str | None
    tz: str
    max_active_triggers: int
    model: str
    jobstore_path: Path
    triggers_dir: Path


def load() -> Settings:
    root = _repo_root()
    return Settings(
        repo_root=root,
        neo4j_uri=_env("NEO4J_URI", "bolt://localhost:7687") or "bolt://localhost:7687",
        neo4j_user=_env("NEO4J_USER", "neo4j") or "neo4j",
        neo4j_password=_env("NEO4J_PASSWORD", "password") or "password",
        neo4j_database=_env("NEO4J_DATABASE", "neo4j") or "neo4j",
        diffbot_api_key=_env("DIFFBOT_API_KEY"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        tz=_env("BRAIN_TZ", "UTC") or "UTC",
        max_active_triggers=int(_env("BRAIN_MAX_ACTIVE_TRIGGERS", "20") or "20"),
        model=_env("BRAIN_MODEL", "claude-sonnet-4-6") or "claude-sonnet-4-6",
        jobstore_path=root / (_env("BRAIN_JOBSTORE", ".brain/jobstore.sqlite") or ".brain/jobstore.sqlite"),
        triggers_dir=root / (_env("BRAIN_TRIGGERS_DIR", "triggers") or "triggers"),
    )


SETTINGS = load()

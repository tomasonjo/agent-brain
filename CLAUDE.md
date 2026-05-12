# agent-brain — code rules

This repo is the agent's own canvas. The same LLM that talks to the user may
also edit code here. Keep the surface stable and the audit trail clean.

## Stack

- Python 3.11+, `uv` for env, `ruff` for lint, `pytest` for tests.
- Run `pytest -q` before any code commit. Run `ruff check .` too.

## Adding things

- **New MCP tool** → `brain/mcp_server/server.py`, plus a test in `tests/`.
  Keep the tool surface minimal: prefer overloading a single `*_upsert` over
  adding a verb-per-action.
- **New flow** → `brain/flows/<name>.py` with signature
  `def run(params: dict, *, fire_id: str) -> list[str]` returning written
  memory paths. Register it in `brain/flows/__init__.py`.
- **New trigger field** → add to `brain/mcp_server/validation.py` first.
- **New ingestion source** → `brain/ingestion/<source>.py`.

## Schema

- Never edit `brain/store/schema.cypher` without adding a migration in
  `brain/store/migrations/` (numbered).
- Memory paths follow `^[a-z][a-z0-9_-]*(/[a-z0-9._-]+)+$` — see
  `validation.py`. Don't loosen without consulting the user.

## Triggers

- Triggers are local YAML in `triggers/`. The MCP `trigger_upsert` writes them.
- Don't delete a `pinned: true` trigger.
- `brain validate` must pass before considering a trigger change done.

## Hooks

- `brain/hooks/log_event.py` and `inject_memory.py` are load-bearing. Never
  add `sys.exit(non-zero)` from these — failing hooks must not block the
  harness.
- Hook scripts read JSON on stdin. Don't add interactive prompts.
- `log_event.py` spawns `dream_session` detached after Stop events. The
  spawned process inherits env. If you change how flows are invoked, update
  the `_spawn_session_dream` call to match.

## Style

- No comments unless the WHY is non-obvious.
- Don't add backwards-compat shims when you can change the code.
- One-file change is fine — don't refactor surrounding code unless asked.

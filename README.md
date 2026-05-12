# agent-brain

A single-user agentic brain. Persistent memory + scheduled flows + MCP access
plane, working across Claude Code, Codex, and Cursor.

## Pieces

- **Hooks** (`brain/hooks/`) — log every event to Neo4j as an `:Event` chain;
  on session start, inject relevant `:Memory` nodes as additional context.
  Empty DB triggers an onboarding system-prompt.
- **MCP server** (`brain/mcp_server/`) — 10 tools the LLM uses to read/write
  memory, manage triggers and plans, and inspect system state.
- **Flows** (`brain/flows/`) — Python functions invoked on a schedule or hook.
  - `daily_brief`: Diffbot fetch → summarize → write memories (cron).
  - `dream_session`: distills a session's events into memories (auto-fires
    from the Stop hook; debounced).
  - `dream_synthesis`: walks the last N days of memories for themes
    (optional cron trigger).
- **Scheduler** (`brain/scheduler/`) — APScheduler daemon that watches
  `triggers/*.yaml` and fires the matching flow.

## Setup

```bash
uv sync
cp .env.example .env             # fill NEO4J_*, DIFFBOT_API_KEY, ANTHROPIC_API_KEY
brain init-db                    # apply schema
brain scheduler &                # background daemon for cron flows
```

Then run a client in the repo root:

```bash
claude                            # or: codex, cursor
```

First session: the DB is empty, so `inject_memory` emits an onboarding prompt
and the agent walks you through identity + interests + daily routines.

## Layout

```
brain/
  hooks/               session/tool event logging + memory injection
  mcp_server/          FastMCP tools
  flows/               scheduled work (daily_brief, ...)
  ingestion/           external sources (diffbot)
  scheduler/           apscheduler boot + trigger reload
  store/               neo4j driver, schema, repo helpers
  cli/                 brain CLI
triggers/              one YAML per scheduled flow instance
prompts/               onboarding text loaded by hooks
.claude/  .codex/  .cursor/   per-client hook wiring + skill
```

## Stack

Neo4j (memory + stats), FastMCP (LLM access), APScheduler + watchdog
(cron + hot reload), Diffbot (article ingestion), Anthropic SDK
(summarization).

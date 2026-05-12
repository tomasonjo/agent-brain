#!/bin/bash
# Hook wrapper: emit additional context for Claude Code. Stdout matters; keep it clean.
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"
if command -v uv >/dev/null 2>&1; then
  uv run --quiet python -m brain.hooks.inject_memory --client claude_code
else
  python3 -m brain.hooks.inject_memory --client claude_code
fi

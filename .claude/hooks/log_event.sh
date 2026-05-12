#!/bin/bash
# Hook wrapper: pipe stdin into brain.hooks.log_event for Claude Code.
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"
{
  if command -v uv >/dev/null 2>&1; then
    uv run --quiet python -m brain.hooks.log_event --client claude_code
  else
    python3 -m brain.hooks.log_event --client claude_code
  fi
} || true

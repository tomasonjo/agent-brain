"""Apply schema.cypher (and future numbered migrations) idempotently."""

from __future__ import annotations

from pathlib import Path

from brain.store.client import session_scope

SCHEMA_FILE = Path(__file__).with_name("schema.cypher")


def _split_statements(text: str) -> list[str]:
    stmts: list[str] = []
    for raw in text.split(";"):
        s = raw.strip()
        if s and not s.startswith("//"):
            stmts.append(s)
    return stmts


def apply_schema() -> int:
    text = SCHEMA_FILE.read_text()
    statements = _split_statements(text)
    with session_scope() as sess:
        for stmt in statements:
            sess.run(stmt)
    return len(statements)


def apply_all() -> dict:
    n = apply_schema()
    return {"schema_statements_applied": n}

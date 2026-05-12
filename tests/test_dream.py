"""Tests for dream helpers (parse, format, debounce). No Neo4j or Anthropic needed."""

from __future__ import annotations

import time

import pytest

from brain.flows._dream_common import (
    format_session_transcript,
    parse_json_array,
    valid_path,
)


class TestParseJsonArray:
    def test_plain_array(self):
        out = parse_json_array('[{"path": "learned/x", "content": "y"}]')
        assert out == [{"path": "learned/x", "content": "y"}]

    def test_with_fences(self):
        out = parse_json_array('```json\n[{"path": "p/q", "content": "c"}]\n```')
        assert out == [{"path": "p/q", "content": "c"}]

    def test_with_prose_around(self):
        text = 'Sure, here is what I found:\n[{"path": "a/b", "content": "c"}]\nHope it helps.'
        out = parse_json_array(text)
        assert out == [{"path": "a/b", "content": "c"}]

    def test_empty_array(self):
        assert parse_json_array("[]") == []

    def test_garbage(self):
        assert parse_json_array("nothing here") == []
        assert parse_json_array("") == []

    def test_not_an_array_returns_empty(self):
        assert parse_json_array('{"path": "a/b"}') == []


class TestFormatTranscript:
    def test_user_and_assistant_only(self):
        events = [
            {"event_name": "SessionStart"},
            {"event_name": "UserPromptSubmit", "prompt": "hello"},
            {"event_name": "PreToolUse", "tool_name": "Bash"},
            {"event_name": "PostToolUse", "tool_response": "out"},
            {"event_name": "Stop", "last_assistant_message": "hi back"},
        ]
        out = format_session_transcript(events)
        assert "USER: hello" in out
        assert "ASSISTANT: hi back" in out
        assert "Bash" not in out  # tool calls excluded

    def test_truncation(self):
        events = [{"event_name": "UserPromptSubmit", "prompt": "x" * 30_000}]
        out = format_session_transcript(events, max_chars=1000)
        assert len(out) <= 1100
        assert "[truncated]" in out

    def test_handles_codex_alias(self):
        events = [{"event_name": "BeforeSubmitPrompt", "prompt": "from codex"}]
        out = format_session_transcript(events)
        assert "USER: from codex" in out

    def test_empty(self):
        assert format_session_transcript([]) == ""


class TestValidPath:
    @pytest.mark.parametrize(
        "p", ["learned/x", "profile/role", "synthesis/week-19", "notes/2026-05-12-foo"]
    )
    def test_ok(self, p):
        assert valid_path(p)

    @pytest.mark.parametrize("p", [None, "", "BAD/path", "no-slash", "/leading"])
    def test_bad(self, p):
        assert not valid_path(p)


class TestDebounce:
    def test_first_call_proceeds_second_skips(self, tmp_path, monkeypatch):
        # Point dream lock dir at a tmp path by monkeypatching SETTINGS.repo_root
        import brain.flows.dream_session as ds

        class _Stub:
            pass

        stub = _Stub()
        stub.repo_root = tmp_path
        monkeypatch.setattr(ds, "SETTINGS", stub)
        assert ds._debounce_ok("sess-1", seconds=10) is True
        assert ds._debounce_ok("sess-1", seconds=10) is False

    def test_after_window_proceeds_again(self, tmp_path, monkeypatch):
        import brain.flows.dream_session as ds

        class _Stub:
            pass

        stub = _Stub()
        stub.repo_root = tmp_path
        monkeypatch.setattr(ds, "SETTINGS", stub)
        assert ds._debounce_ok("sess-2", seconds=1) is True
        time.sleep(1.1)
        assert ds._debounce_ok("sess-2", seconds=1) is True

    def test_different_sessions_independent(self, tmp_path, monkeypatch):
        import brain.flows.dream_session as ds

        class _Stub:
            pass

        stub = _Stub()
        stub.repo_root = tmp_path
        monkeypatch.setattr(ds, "SETTINGS", stub)
        assert ds._debounce_ok("a", seconds=10) is True
        assert ds._debounce_ok("b", seconds=10) is True


def test_flow_registry_has_dreams():
    from brain.flows import FLOWS

    assert "dream_session" in FLOWS
    assert "dream_synthesis" in FLOWS

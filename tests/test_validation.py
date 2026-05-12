"""Pure-Python validation tests. No Neo4j needed."""

from __future__ import annotations

import pytest

from brain.mcp_server.validation import (
    validate_memory_path,
    validate_trigger_config,
    validate_trigger_id,
)


class TestMemoryPath:
    @pytest.mark.parametrize(
        "p",
        [
            "profile/role",
            "preferences/communication-style",
            "topics/ai",
            "notes/2026-05-12-foo",
            "learned/diffbot-rate-limits",
            "topics/polynesian-travel",
        ],
    )
    def test_ok(self, p):
        validate_memory_path(p)

    @pytest.mark.parametrize(
        "p",
        [
            "PROFILE/role",
            "profile",
            "/profile/role",
            "profile//role",
            "1profile/role",
            "profile/role!",
        ],
    )
    def test_bad(self, p):
        with pytest.raises(ValueError):
            validate_memory_path(p)


class TestTriggerId:
    @pytest.mark.parametrize("tid", ["ai_news_brief", "weekly_review", "a"])
    def test_ok(self, tid):
        validate_trigger_id(tid)

    @pytest.mark.parametrize("tid", ["AI", "1foo", "with-dash", ""])
    def test_bad(self, tid):
        with pytest.raises(ValueError):
            validate_trigger_id(tid)


class TestTriggerConfig:
    @property
    def good(self):
        return {
            "flow": "daily_brief",
            "schedule": {"type": "cron", "expr": "0 7 * * 1-5", "tz": "UTC"},
            "params": {"topic_path": "topics/ai"},
            "status": "active",
            "pinned": False,
            "description": "ok",
        }

    def test_ok(self):
        normalized = validate_trigger_config(self.good, known_flows={"daily_brief"})
        assert normalized["flow"] == "daily_brief"
        assert normalized["schedule"]["expr"] == "0 7 * * 1-5"
        assert normalized["status"] == "active"

    def test_unknown_flow(self):
        with pytest.raises(ValueError, match="unknown flow"):
            validate_trigger_config(self.good, known_flows={"other"})

    def test_bad_cron(self):
        bad = dict(self.good)
        bad["schedule"] = {"type": "cron", "expr": "not a cron", "tz": "UTC"}
        with pytest.raises(ValueError, match="invalid cron"):
            validate_trigger_config(bad, known_flows={"daily_brief"})

    def test_bad_status(self):
        bad = dict(self.good)
        bad["status"] = "wat"
        with pytest.raises(ValueError, match="status"):
            validate_trigger_config(bad, known_flows={"daily_brief"})

    def test_missing_flow(self):
        bad = dict(self.good)
        del bad["flow"]
        with pytest.raises(ValueError, match="flow"):
            validate_trigger_config(bad, known_flows={"daily_brief"})

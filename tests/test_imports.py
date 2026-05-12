"""Sanity: every module imports cleanly. Does NOT require Neo4j running."""

from __future__ import annotations


def test_imports():
    import brain  # noqa: F401
    import brain.cli.brain  # noqa: F401
    import brain.config  # noqa: F401
    import brain.flows  # noqa: F401
    import brain.flows.daily_brief  # noqa: F401
    import brain.hooks.common  # noqa: F401
    import brain.hooks.inject_memory  # noqa: F401
    import brain.hooks.log_event  # noqa: F401
    import brain.ingestion.diffbot  # noqa: F401
    import brain.mcp_server.server  # noqa: F401
    import brain.mcp_server.validation  # noqa: F401
    import brain.scheduler.dispatcher  # noqa: F401
    import brain.scheduler.loader  # noqa: F401
    import brain.scheduler.main  # noqa: F401
    import brain.store  # noqa: F401
    import brain.store.client  # noqa: F401
    import brain.store.migrate  # noqa: F401
    import brain.store.repo  # noqa: F401


def test_flow_registry_populated():
    from brain.flows import FLOWS

    assert "daily_brief" in FLOWS
    assert callable(FLOWS["daily_brief"])

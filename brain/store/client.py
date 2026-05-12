"""Thin Neo4j driver wrapper. Lazy singleton so hooks don't reopen per call."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from neo4j import Driver, GraphDatabase, Session

from brain.config import SETTINGS

_driver: Driver | None = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            SETTINGS.neo4j_uri,
            auth=(SETTINGS.neo4j_user, SETTINGS.neo4j_password),
        )
    return _driver


@contextmanager
def session_scope() -> Iterator[Session]:
    driver = get_driver()
    sess = driver.session(database=SETTINGS.neo4j_database)
    try:
        yield sess
    finally:
        sess.close()


def close() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None

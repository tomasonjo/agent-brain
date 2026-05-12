"""Diffbot query builder — pure-Python."""

from __future__ import annotations

from brain.ingestion.diffbot import build_query


def test_full_query():
    q = build_query(category="Artificial Intelligence", text="openai", date_within="1d")
    assert "type:Article" in q
    assert 'categories.name:"Artificial Intelligence"' in q
    assert 'text:"openai"' in q
    assert "date<1d" in q


def test_no_category_no_text():
    q = build_query()
    assert q == "type:Article date<1d"


def test_extra_appended():
    q = build_query(category="Technology", extra="language:en")
    assert q.endswith("language:en")

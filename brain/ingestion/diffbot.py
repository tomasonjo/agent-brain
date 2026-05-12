"""Diffbot Knowledge Graph search adapter.

Uses the DQL endpoint with a query like:
    type:Article categories.name:"Artificial Intelligence" date<1d text:"openai"

Docs: https://docs.diffbot.com/reference/knowledge-graph-dql
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from brain.config import SETTINGS

DQL_ENDPOINT = "https://kg.diffbot.com/kg/v3/dql"


@dataclass
class Article:
    title: str
    summary: str
    url: str
    site: str | None
    published_at: str | None
    categories: list[str]

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "summary": self.summary,
            "url": self.url,
            "site": self.site,
            "published_at": self.published_at,
            "categories": self.categories,
        }


def build_query(
    *,
    category: str | None = None,
    text: str | None = None,
    date_within: str = "1d",
    extra: str | None = None,
) -> str:
    """Build a DQL query string for Articles.

    - category matches `categories.name:"..."` (Diffbot taxonomy).
    - text is a free-text filter `text:"..."` against article body.
    - date_within e.g. "1d", "3d", "7d" → `date<Nd`.
    - extra is appended verbatim if you need richer DQL.
    """
    parts = ["type:Article"]
    if category:
        parts.append(f'categories.name:"{category}"')
    if text:
        parts.append(f'text:"{text}"')
    if date_within:
        parts.append(f"date<{date_within}")
    if extra:
        parts.append(extra)
    return " ".join(parts)


def search(
    *,
    category: str | None = None,
    text: str | None = None,
    date_within: str = "1d",
    limit: int = 10,
    extra: str | None = None,
) -> list[Article]:
    if not SETTINGS.diffbot_api_key:
        raise RuntimeError("DIFFBOT_API_KEY is not set in .env")
    query = build_query(category=category, text=text, date_within=date_within, extra=extra)
    params = {
        "type": "query",
        "token": SETTINGS.diffbot_api_key,
        "query": query,
        "size": str(min(limit, 50)),
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(DQL_ENDPOINT, params=params)
        resp.raise_for_status()
        body = resp.json()
    items = body.get("data") or []
    out: list[Article] = []
    for it in items[:limit]:
        out.append(
            Article(
                title=it.get("title") or it.get("name") or "(untitled)",
                summary=it.get("summary") or it.get("text", "")[:1000],
                url=it.get("pageUrl") or it.get("url", ""),
                site=(it.get("siteName") or it.get("site")),
                published_at=it.get("date", {}).get("str") if isinstance(it.get("date"), dict) else it.get("date"),
                categories=[c.get("name") for c in (it.get("categories") or []) if c.get("name")],
            )
        )
    return out

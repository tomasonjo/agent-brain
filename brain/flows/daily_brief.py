"""Daily news brief: fetch Diffbot articles for a topic, summarize, write memories.

params:
    topic_path: str         e.g. "topics/ai" — read for category / text filter / display name
    max_articles: int       default 10
    date_within: str        default "1d"
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from anthropic import Anthropic

from brain.config import SETTINGS
from brain.ingestion import diffbot
from brain.store import repo

SUMMARIZE_SYSTEM = (
    "You write tight, signal-dense article summaries for a personal daily brief. "
    "Two to four sentences max. Lead with the fact, not the framing. "
    "Skip 'this article discusses' fluff."
)


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "topic"


def _summarize(client: Anthropic, article: diffbot.Article) -> str:
    msg = (
        f"Title: {article.title}\n"
        f"URL: {article.url}\n"
        f"Site: {article.site or 'unknown'}\n"
        f"Date: {article.published_at or 'unknown'}\n\n"
        f"Body:\n{article.summary}"
    )
    resp = client.messages.create(
        model=SETTINGS.model,
        max_tokens=300,
        system=SUMMARIZE_SYSTEM,
        messages=[{"role": "user", "content": msg}],
    )
    return "".join(b.text for b in resp.content if hasattr(b, "text")).strip()


def run(params: dict, *, fire_id: str) -> list[str]:
    topic_path = params.get("topic_path")
    if not topic_path:
        raise ValueError("daily_brief requires params.topic_path")
    topic_mem = repo.memory_get_by_path(topic_path)
    if not topic_mem:
        raise KeyError(f"topic memory not found: {topic_path}")

    meta = topic_mem.get("metadata") or {}
    category = meta.get("diffbot_category")
    text_filter = meta.get("diffbot_text_filter") or None
    date_within = params.get("date_within", "1d")
    limit = int(params.get("max_articles", 10))

    articles = diffbot.search(
        category=category,
        text=text_filter,
        date_within=date_within,
        limit=limit,
    )

    if not articles:
        digest_path = f"notes/{_today()}-{_slugify(topic_path.split('/', 1)[1])}-digest"
        repo.memory_upsert(
            digest_path,
            f"No new {topic_path} articles in the last {date_within}.",
            metadata={"topic": topic_path, "article_count": 0},
            source=f"flow:{fire_id}",
        )
        return [digest_path]

    today = _today()
    topic_slug = _slugify(topic_path.split("/", 1)[1])
    written: list[str] = []
    digest_lines: list[str] = []

    client = Anthropic(api_key=SETTINGS.anthropic_api_key)
    for i, art in enumerate(articles):
        summary = _summarize(client, art)
        path = f"notes/{today}-{topic_slug}-{i:02d}"
        repo.memory_upsert(
            path,
            summary,
            metadata={
                "topic": topic_path,
                "url": art.url,
                "title": art.title,
                "site": art.site,
                "published_at": art.published_at,
                "categories": art.categories,
            },
            source=f"flow:{fire_id}",
        )
        written.append(path)
        digest_lines.append(f"- **{art.title}** ({art.site or '?'}) — {summary}\n  {art.url}")

    digest_path = f"notes/{today}-{topic_slug}-digest"
    repo.memory_upsert(
        digest_path,
        f"# {topic_path} brief — {today}\n\n" + "\n\n".join(digest_lines),
        metadata={"topic": topic_path, "article_count": len(articles)},
        source=f"flow:{fire_id}",
    )
    written.append(digest_path)
    return written

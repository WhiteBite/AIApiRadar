"""Hacker News collector — Show HN launches + free-credit chatter.

Uses the public Algolia HN Search API (no key, no auth). We query recent
stories for offer phrasing and also sweep newest Show HN posts, where AI
startups announce free tiers hours-to-days before they reach Telegram.
"""
from __future__ import annotations

from typing import Iterable

import httpx

from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("hackernews")

API = "https://hn.algolia.com/api/v1/search_by_date"

QUERIES = [
    "free credits api",
    "free api credits claude gpt gemini",
    "free tier ai api",
    "api free trial credits",
]


def parse_results(data: dict, source: str = "hackernews") -> list[Signal]:
    out: list[Signal] = []
    for hit in (data or {}).get("hits", []):
        title = hit.get("title") or hit.get("story_title") or ""
        url = hit.get("url") or hit.get("story_url")
        text_extra = hit.get("story_text") or hit.get("comment_text") or ""
        oid = hit.get("objectID")
        text = f"{title}. {text_extra}".strip(". ").strip()
        if not text and not url:
            continue
        out.append(Signal(
            source=source,
            raw_text=text[:4000],
            url=url or None,
            source_url=f"https://news.ycombinator.com/item?id={oid}" if oid else url,
            meta={"points": hit.get("points")},
        ))
    return out


@register
class HackerNewsCollector(Collector):
    name = "hackernews"
    kind = "api"
    interval = 1800

    def __init__(self, queries: list[str] | None = None, timeout: float = 20.0):
        self.queries = queries or QUERIES
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        async with httpx.AsyncClient(timeout=self.timeout,
                                     headers={"User-Agent": "AiApiRadar/0.1"}) as client:
            # keyword queries (stories only)
            for q in self.queries:
                try:
                    r = await client.get(API, params={
                        "query": q, "tags": "story", "hitsPerPage": 20,
                    })
                    if r.status_code == 200:
                        out.extend(parse_results(r.json()))
                except Exception:
                    log.warning("hn query failed: %s", q[:30], exc_info=False)
            # newest Show HN sweep (launches, classifier decides)
            try:
                r = await client.get(API, params={"tags": "show_hn", "hitsPerPage": 40})
                if r.status_code == 200:
                    out.extend(parse_results(r.json()))
            except Exception:
                log.warning("hn show_hn sweep failed", exc_info=False)
        log.info("hackernews collected %d items", len(out))
        return out

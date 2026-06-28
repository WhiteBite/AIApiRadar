"""Changelog/blog RSS collector — AI-platform announcements.

New free-tier / trial / model offers usually land on a platform's changelog or
blog before they surface on Telegram or forums. We watch a curated, easily
extended list of public RSS feeds (no key) and emit each entry as a Signal.

To add a feed: drop another `source_key -> url` pair into FEEDS. Each feed is
fetched independently and guarded — a dead URL just logs at DEBUG.
"""
from __future__ import annotations

import html
import re
from typing import Iterable

import feedparser
import httpx

from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("changelog_rss")

# source_key -> RSS/Atom URL. All public; extend freely.
FEEDS = {
    "or_changelog":   "https://openrouter.ai/changelog/rss",
    "hf_blog":        "https://huggingface.co/blog/feed.xml",
    "together_blog":  "https://www.together.ai/blog/rss.xml",
    "groq_blog":      "https://groq.com/feed/",
    "mistral_news":   "https://mistral.ai/news/rss.xml",
    "fireworks_blog": "https://fireworks.ai/blog/rss.xml",
    "deepinfra_blog": "https://deepinfra.com/blog/feed.xml",
    "replicate_blog": "https://replicate.com/blog/rss",
}

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", text or "")).strip()


def parse_changelog(content: str | bytes, key: str) -> list[Signal]:
    """Pure parse: feed XML -> Signals tagged with feed key. No network."""
    parsed = feedparser.parse(content)
    out: list[Signal] = []
    for entry in parsed.entries:
        title = _clean(getattr(entry, "title", ""))
        summary = _clean(getattr(entry, "summary", ""))
        link = getattr(entry, "link", None)
        text = f"{title}. {summary}".strip()
        if not text and not link:
            continue
        out.append(Signal(
            source="changelog",
            raw_text=text[:8000],
            source_url=link,
            meta={"feed": key},
        ))
    return out


@register
class ChangelogCollector(Collector):
    name = "changelog_rss"
    kind = "rss"
    interval = 3600  # hourly

    def __init__(self, feeds: dict[str, str] | None = None, timeout: float = 20.0):
        self.feeds = feeds or FEEDS
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True,
                                     headers={"User-Agent": "AiApiRadar/0.1"}) as client:
            for key, url in self.feeds.items():
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    out.extend(parse_changelog(resp.content, key))
                except Exception:
                    log.debug("changelog feed failed: %s", key, exc_info=False)
        log.info("changelog_rss collected %d entries", len(out))
        return out

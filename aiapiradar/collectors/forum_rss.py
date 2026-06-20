"""Forum RSS collector — nodeseek / linux.do / v2ex.

These Chinese/dev forums are the epicentre for API-relay (中转站) launches.
All expose RSS, readable without login. We parse entries into Signals; the
pre-filter + classifier decide which are actual offers.
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

log = get_logger("forum_rss")

# Per-feed source name -> RSS URL. Tune endpoints in config later.
FEEDS = {
    "nodeseek": "https://rss.nodeseek.com/",
    "linuxdo": "https://linux.do/latest.rss",
    "v2ex": "https://www.v2ex.com/feed/tab/all.xml",
}

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", text or "")).strip()


def parse_feed(content: str | bytes, source: str) -> list[Signal]:
    """Pure parse: feed XML -> Signals. No network."""
    parsed = feedparser.parse(content)
    signals: list[Signal] = []
    for entry in parsed.entries:
        title = _clean(getattr(entry, "title", ""))
        summary = _clean(getattr(entry, "summary", ""))
        link = getattr(entry, "link", None)
        text = f"{title}. {summary}".strip()
        if not text and not link:
            continue
        signals.append(Signal(
            source=source,
            raw_text=text[:8000],
            source_url=link,
            meta={"feed_title": title},
        ))
    return signals


@register
class ForumRssCollector(Collector):
    name = "forum_rss"
    kind = "rss"
    interval = 600

    def __init__(self, feeds: dict[str, str] | None = None, timeout: float = 20.0):
        self.feeds = feeds or FEEDS
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True,
                                     headers={"User-Agent": "AiApiRadar/0.1"}) as client:
            for source, url in self.feeds.items():
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    out.extend(parse_feed(resp.content, source))
                except Exception:
                    log.warning("forum feed failed: %s", source, exc_info=False)
        log.info("forum_rss collected %d entries", len(out))
        return out

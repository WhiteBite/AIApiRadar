"""Product Hunt collector — new launches via public RSS (no token needed).

Legit SaaS often launch here; the free-tier detail is decided downstream by
the classifier.
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

log = get_logger("producthunt")

FEED_URL = "https://www.producthunt.com/feed"
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(t: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", t or "")).strip()


def parse_feed(content: str | bytes) -> list[Signal]:
    parsed = feedparser.parse(content)
    out: list[Signal] = []
    for e in parsed.entries:
        title = _clean(getattr(e, "title", ""))
        summary = _clean(getattr(e, "summary", ""))
        link = getattr(e, "link", None)
        text = f"{title}. {summary}".strip()
        if not text and not link:
            continue
        out.append(Signal(source="producthunt", raw_text=text[:4000], source_url=link))
    return out


@register
class ProductHuntCollector(Collector):
    name = "producthunt"
    kind = "rss"
    interval = 1800

    def __init__(self, feed_url: str = FEED_URL, timeout: float = 20.0):
        self.feed_url = feed_url
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0 AiApiRadar/0.1"}) as client:
            try:
                r = await client.get(self.feed_url)
                if r.status_code == 200:
                    out = parse_feed(r.content)
            except Exception:
                log.warning("producthunt feed failed", exc_info=False)
        log.info("producthunt collected %d entries", len(out))
        return out

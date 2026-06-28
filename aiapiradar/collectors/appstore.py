"""App Store collector — new/updated AI apps via Apple's public RSS feeds.

Apple publishes free, key-less RSS feeds (the "Marketing Tools" feeds). We pull
several feeds of the same JSON shape — top-free, new-apps-we-love, top-grossing —
to catch freshly-launched/featured ("what's new") apps, then keep only entries
whose name matches an AI keyword regex. Many consumer AI apps ship free trials —
adjacent to API offers, but a valid discovery signal.

RSS can't be keyword-searched, so we fetch the broad top-free list and filter
client-side. Network is guarded → empty list on any failure.
"""
from __future__ import annotations

import re
from typing import Iterable

import httpx

from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("appstore")

FEED_URLS = (
    "https://rss.applemarketingtools.com/api/v2/us/apps/top-free/50/apps.json",
    "https://rss.applemarketingtools.com/api/v2/us/apps/new-apps-we-love/50/apps.json",
    "https://rss.applemarketingtools.com/api/v2/us/apps/top-grossing/25/apps.json",
)

_AI_RE = re.compile(r"ai|gpt|chat|llm|assistant|claude|gemini", re.IGNORECASE)


def parse_appstore(data: dict) -> list[Signal]:
    """Pure parse: Apple RSS `feed.results[]` -> AI-filtered Signals. No network."""
    out: list[Signal] = []
    results = ((data or {}).get("feed") or {}).get("results") or []
    for app in results:
        name = app.get("name") or ""
        if not name or not _AI_RE.search(name):
            continue
        artist = app.get("artistName") or ""
        app_url = app.get("url") or None
        out.append(Signal(
            source="appstore",
            raw_text=f"{name} — {artist}".strip(" —"),
            url=app_url,
            meta={},
        ))
    return out


@register
class AppStoreCollector(Collector):
    name = "appstore"
    kind = "api"
    interval = 43200  # 12h

    def __init__(self, timeout: float = 25.0):
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        seen: set[str] = set()
        headers = {"User-Agent": "AiApiRadar/0.1"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True,
                                         headers=headers) as client:
                for feed_url in FEED_URLS:
                    try:
                        r = await client.get(feed_url)
                        if r.status_code != 200:
                            log.warning("appstore feed %s -> %s", feed_url, r.status_code)
                            continue
                        for sig in parse_appstore(r.json()):
                            key = sig.url or sig.raw_text
                            if key in seen:
                                continue
                            seen.add(key)
                            out.append(sig)
                    except Exception:
                        log.warning("appstore feed %s failed", feed_url, exc_info=False)
        except Exception:
            log.warning("appstore collect failed", exc_info=False)
        log.info("appstore collected %d apps", len(out))
        return out

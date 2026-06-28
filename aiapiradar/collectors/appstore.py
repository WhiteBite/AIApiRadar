"""App Store collector — new/updated AI apps via Apple's public RSS feeds.

Apple publishes free, key-less RSS feeds (the "Marketing Tools" feeds). We pull
the top-free apps and keep only entries whose name matches an AI keyword regex.
Many consumer AI apps ship free trials — adjacent to API offers, but a valid
discovery signal.

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

FEED_URL = (
    "https://rss.applemarketingtools.com/api/v2/us/apps/top-free/50/apps.json"
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
        headers = {"User-Agent": "AiApiRadar/0.1"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True,
                                         headers=headers) as client:
                r = await client.get(FEED_URL)
                if r.status_code == 200:
                    out = parse_appstore(r.json())
                else:
                    log.warning("appstore feed -> %s", r.status_code)
        except Exception:
            log.warning("appstore collect failed", exc_info=False)
        log.info("appstore collected %d apps", len(out))
        return out

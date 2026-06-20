"""YouTube collector — recent videos about AI credits / giveaways.

Creators often cover new free-credit methods; we search the last 24h for
relevant keywords. Requires AIRADAR_YOUTUBE_API_KEY; no-op without it.
"""
from __future__ import annotations

import datetime as dt
from typing import Iterable

import httpx

from ..config import get_settings
from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("youtube")

QUERIES = [
    "free AI API credits",
    "free claude gpt gemini api",
    "中转站 注册送",
    "бесплатные кредиты api нейросети",
]

ENDPOINT = "https://www.googleapis.com/youtube/v3/search"


def parse_search(data: dict, source: str = "youtube") -> list[Signal]:
    out: list[Signal] = []
    for item in (data or {}).get("items", []):
        vid = (item.get("id") or {}).get("videoId")
        snip = item.get("snippet") or {}
        title = snip.get("title") or ""
        desc = snip.get("description") or ""
        if not vid:
            continue
        text = f"{title}. {desc}".strip()
        out.append(Signal(
            source=source,
            raw_text=text[:2000],
            url=f"https://youtu.be/{vid}",
            source_url=f"https://youtu.be/{vid}",
        ))
    return out


@register
class YouTubeCollector(Collector):
    name = "youtube"
    kind = "api"
    interval = 3600

    def __init__(self, queries: list[str] | None = None, timeout: float = 25.0):
        self.queries = queries or QUERIES
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        key = get_settings().youtube_api_key
        if not key:
            log.info("youtube disabled (no YOUTUBE_API_KEY)")
            return []
        published_after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)) \
            .replace(microsecond=0).isoformat().replace("+00:00", "Z")
        out: list[Signal] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for q in self.queries:
                try:
                    r = await client.get(ENDPOINT, params={
                        "key": key, "q": q, "part": "snippet", "type": "video",
                        "order": "date", "publishedAfter": published_after, "maxResults": 10,
                    })
                    if r.status_code == 200:
                        out.extend(parse_search(r.json()))
                except Exception:
                    log.warning("youtube query failed", exc_info=False)
        log.info("youtube collected %d videos", len(out))
        return out

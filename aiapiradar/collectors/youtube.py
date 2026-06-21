"""YouTube collector — recent videos about AI credits / giveaways.

Creators often cover new free-credit methods; we search the last 24h for
relevant keywords. Requires AIRADAR_YOUTUBE_API_KEY; no-op without it.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Iterable

import httpx

from ..config import get_settings
from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("youtube")

_URL_RE = re.compile(r"https?://\S+")

# Each entry: required "q", optional "relevanceLanguage", optional "regionCode"
QUERY_PARAMS: list[dict] = [
    # English
    {"q": "free AI API credits", "relevanceLanguage": "en"},
    {"q": "free claude gpt gemini api", "relevanceLanguage": "en"},
    {"q": "free AI API key no credit card", "relevanceLanguage": "en"},
    {"q": "AI API free tier tutorial", "relevanceLanguage": "en"},
    # Chinese (中转站 scene - core of the relay ecosystem)
    {"q": "中转站 注册送", "relevanceLanguage": "zh", "regionCode": "CN"},
    {"q": "免费 API claude gpt 注册", "relevanceLanguage": "zh", "regionCode": "CN"},
    {"q": "AI API 白嫖 教程", "relevanceLanguage": "zh", "regionCode": "CN"},
    {"q": "免费额度 API 申请", "relevanceLanguage": "zh", "regionCode": "CN"},
    # Russian
    {"q": "бесплатные кредиты api нейросети", "relevanceLanguage": "ru"},
    {"q": "бесплатный api claude gpt регистрация", "relevanceLanguage": "ru"},
    {"q": "промокод AI API бесплатно", "relevanceLanguage": "ru"},
    # Korean
    {"q": "무료 AI API 크레딧", "relevanceLanguage": "ko"},
    {"q": "무료 API 클로드 GPT", "relevanceLanguage": "ko"},
    # Vietnamese
    {"q": "API miễn phí AI đăng ký", "relevanceLanguage": "vi"},
    {"q": "Claude GPT API miễn phí", "relevanceLanguage": "vi"},
    # Hindi
    {"q": "मुफ्त AI API क्रेडिट", "relevanceLanguage": "hi"},
    # Japanese
    {"q": "無料 AI API クレジット", "relevanceLanguage": "ja"},
]

# Flat list of query strings — kept for backward compatibility and tests
QUERIES = [p["q"] for p in QUERY_PARAMS]

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
        # Extract URLs from description so the harvest pipeline can pick up relay domains
        urls_found = _URL_RE.findall(desc)
        if urls_found:
            text = text + "\n" + " ".join(urls_found)
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
        # When custom queries are passed (e.g. in tests), wrap as minimal param dicts
        if queries is not None:
            self.query_params = [{"q": q} for q in queries]
            self.queries = queries
        else:
            self.query_params = QUERY_PARAMS
            self.queries = QUERIES
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
            for qp in self.query_params:
                try:
                    params = {
                        "key": key,
                        "q": qp["q"],
                        "part": "snippet",
                        "type": "video",
                        "order": "date",
                        "publishedAfter": published_after,
                        "maxResults": 10,
                    }
                    if "relevanceLanguage" in qp:
                        params["relevanceLanguage"] = qp["relevanceLanguage"]
                    if "regionCode" in qp:
                        params["regionCode"] = qp["regionCode"]
                    r = await client.get(ENDPOINT, params=params)
                    if r.status_code == 200:
                        out.extend(parse_search(r.json()))
                except Exception:
                    log.warning("youtube query failed", exc_info=False)
        log.info("youtube collected %d videos", len(out))
        return out

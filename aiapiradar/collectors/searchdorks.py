"""Search-dork collector — Google Programmable Search (Custom Search JSON API).

Promo/landing pages get indexed within hours. We run targeted dorks. Requires
AIRADAR_SEARCH_API_KEY + AIRADAR_SEARCH_CX; degrades to no-op without them.
"""
from __future__ import annotations

from typing import Iterable

import httpx

from ..config import get_settings
from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("searchdorks")

DORKS = [
    '"free credits" "sign up" (claude OR gpt OR gemini) -site:reddit.com',
    'inurl:redeem OR inurl:promo "$" api credits',
    'site:nodeseek.com 注册送 额度',
    'site:linux.do 公益站 免费 API',
    'site:v2ex.com 中转站 注册送',
    '"no credit card" free api credits register',
    '白嫖 claude code api 注册送',
    'API ключи триальный баланс регистрация бесплатно',
]

ENDPOINT = "https://www.googleapis.com/customsearch/v1"


def parse_results(data: dict, source: str = "searchdorks") -> list[Signal]:
    out: list[Signal] = []
    for item in (data or {}).get("items", []):
        title = item.get("title") or ""
        snippet = item.get("snippet") or ""
        link = item.get("link")
        text = f"{title}. {snippet}".strip()
        if not link:
            continue
        out.append(Signal(source=source, raw_text=text[:2000], url=link, source_url=link))
    return out


@register
class SearchDorksCollector(Collector):
    name = "searchdorks"
    kind = "api"
    interval = 3600

    def __init__(self, dorks: list[str] | None = None, timeout: float = 25.0):
        self.dorks = dorks or DORKS
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        s = get_settings()
        if not (s.search_api_key and s.search_cx):
            log.info("searchdorks disabled (no SEARCH_API_KEY/SEARCH_CX)")
            return []
        out: list[Signal] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for q in self.dorks:
                try:
                    r = await client.get(ENDPOINT, params={
                        "key": s.search_api_key, "cx": s.search_cx, "q": q,
                        "dateRestrict": "d1", "num": 10,
                    })
                    if r.status_code == 200:
                        out.extend(parse_results(r.json()))
                except Exception:
                    log.warning("searchdork failed", exc_info=False)
        log.info("searchdorks collected %d results", len(out))
        return out

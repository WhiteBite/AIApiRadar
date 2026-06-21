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
    # ── Broad discovery: catches ANY new site, not just known ones ─────────
    # When BandAI publishes "promo code BANDHACK26" on band.ai,
    # this query returns it within hours — no prior knowledge of band.ai needed.
    '"promo code" AI API free -site:reddit.com -site:twitter.com -site:youtube.com',
    '"free trial" LLM API -site:reddit.com -site:openai.com -site:anthropic.com',
    '"free credits" AI API "sign up" -site:reddit.com',
    '"no credit card" AI API free tier launch',

    # Fresh .ai / .io domains with promo offers (catches new startups)
    '(site:*.ai OR site:*.io) "promo code" "free" API',
    '(site:*.ai OR site:*.io) "free tier" OR "free trial" API launch',

    # Hackathon promos: "BANDHACK26"-style codes always contain HACK/FEST/DEV
    # and appear on hackathon platform sponsor pages before TG channels pick them up
    '(site:lablab.ai OR site:devpost.com OR site:hackathon.io) "free" "API" promo',

    # AppSumo / deal aggregators: established services run limited-time promos here
    'site:appsumo.com AI API "free" OR "lifetime" -"sold out"',
    'site:saasworthy.com "free trial" AI API new',

    # Russian broad discovery (not site-specific)
    '"промокод" AI API бесплатно -reddit -telegram',
    'бесплатный триал API AI сервис регистрация',

    # Chinese relay / free API discovery (site-specific — high signal)
    'site:nodeseek.com 注册送 额度',
    'site:linux.do 公益站 免费 API',
    'site:v2ex.com 中转站 注册送',
    '白嫖 claude code api 注册送',
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

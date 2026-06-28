"""Y Combinator collector — recent AI companies from the public YC directory.

The YC company directory at ycombinator.com is backed by a public, read-only
Algolia index. We query it for AI / Developer-Tools companies and emit each
company's website as a discovery candidate — the harvest pipeline + probe
dedup decide whether the underlying service ships a free/trial API.

The Algolia API key below is the public search key embedded in
ycombinator.com's frontend. If it ever rotates and starts returning 4xx, we
catch the error and degrade to an empty result (FALLBACK) rather than crash.
"""
from __future__ import annotations

import json
from typing import Iterable

import httpx

from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("yc")

ALGOLIA_URL = (
    "https://45bwzj1sgc-dsn.algolia.net/1/indexes/YCCompany_production/query"
)

# Public read-only key used by ycombinator.com's company directory.
ALGOLIA_API_KEY = (
    "MTI2YmZjNWY5ZjY2YzhmYzUyZjdkOWZhMDg2OWNhNjk0NzhkMmM4ZGRkOTI4NDNlMTI2NWU3"
    "NWM2MmQ4NWFjNHRhZ0ZpbHRlcnM9JTVCJTIyeWNkY19wdWJsaWMlMjIlNUQ%3D"
)
ALGOLIA_APP_ID = "45BWZJ1SGC"

_QUERY_BODY = {
    "query": "",
    "hitsPerPage": 50,
    "filters": (
        '(industries:"Artificial Intelligence" OR '
        'industries:"Developer Tools" OR tags:"AI")'
    ),
    "page": 0,
}


def parse_yc(data: dict) -> list[Signal]:
    """Pure parse: Algolia `{hits:[...]}` response -> Signals. No network."""
    out: list[Signal] = []
    for hit in (data or {}).get("hits", []):
        name = hit.get("name") or ""
        if not name:
            continue
        website = hit.get("website") or None
        one_liner = hit.get("one_liner") or ""
        batch = hit.get("batch") or ""
        out.append(Signal(
            source="yc",
            raw_text=f"{name} ({batch}). {one_liner}".strip(),
            url=website,
            meta={"service_candidate": True, "batch": batch},
        ))
    return out


@register
class YCCollector(Collector):
    name = "yc"
    kind = "api"
    interval = 86400  # daily — the directory changes slowly

    def __init__(self, timeout: float = 25.0):
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        headers = {
            "User-Agent": "AiApiRadar/0.1",
            "X-Algolia-API-Key": ALGOLIA_API_KEY,
            "X-Algolia-Application-Id": ALGOLIA_APP_ID,
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
                r = await client.post(ALGOLIA_URL, content=json.dumps(_QUERY_BODY))
                if r.status_code == 200:
                    out = parse_yc(r.json())
                else:
                    # Key rotated / blocked — FALLBACK: degrade gracefully.
                    log.warning("yc algolia -> %s", r.status_code)
        except Exception:
            log.warning("yc collect failed", exc_info=False)
        log.info("yc collected %d companies", len(out))
        return out

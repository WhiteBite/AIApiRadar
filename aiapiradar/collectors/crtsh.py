"""CrtshCollector — polls crt.sh API for new AI-related domains.

Alternative to CertStreamCollector for platforms without persistent WebSocket
support (e.g. Cloudflare Workers Cron, GitHub Actions).

Queries crt.sh for certificates matching AI/relay patterns issued recently.
"""
from __future__ import annotations

from typing import Iterable

import httpx

from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register
from .certstream import domain_matches  # reuse existing keyword filter

log = get_logger("crtsh")

# Search patterns — wildcards for common relay/AI naming patterns
SEARCH_PATTERNS = [
    "%-api.%",
    "%router%",
    "%relay%",
    "%llm%",
    "%aiproxy%",
    "%oneapi%",
    "%freemodel%",
    "%chatapi%",
]

CRTSH_URL = "https://crt.sh/"


@register
class CrtshCollector(Collector):
    name = "crtsh"
    kind = "http-poll"
    interval = 3600  # once per hour — suitable for CF Cron free tier

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        seen: set[str] = set()
        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": "AiApiRadar/0.1"},
        ) as client:
            for pattern in SEARCH_PATTERNS:
                try:
                    r = await client.get(CRTSH_URL, params={
                        "q": pattern,
                        "output": "json",
                        "exclude": "expired",
                    })
                    if r.status_code != 200:
                        continue
                    for entry in r.json() or []:
                        for name_val in (entry.get("name_value") or "").split("\n"):
                            dom = name_val.strip().lstrip("*.")
                            if dom and dom not in seen and domain_matches(dom):
                                seen.add(dom)
                                out.append(Signal(
                                    source=self.name,
                                    raw_text=dom,
                                    url=f"https://{dom}",
                                    source_url=f"https://crt.sh/?q={dom}",
                                    meta={"service_candidate": True, "force_classify": True},
                                ))
                except Exception:
                    log.warning("crtsh pattern %s failed", pattern, exc_info=False)
        log.info("crtsh found %d candidate domains", len(out))
        return out

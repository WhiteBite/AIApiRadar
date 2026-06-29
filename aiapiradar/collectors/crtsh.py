"""CrtshCollector — polls crt.sh API for new AI-related domains.

Alternative to CertStreamCollector for platforms without persistent WebSocket
support (e.g. Cloudflare Workers Cron, GitHub Actions).

Queries crt.sh for certificates matching AI/relay patterns issued recently.

crt.sh aggressively rate-limits shared IPs (GitHub Actions runners get 429s /
hangs constantly). Each query then blocks for the full timeout, and ~24 serial
patterns would burn minutes per run. Two guards keep it bounded:
  * a short per-request timeout, and
  * a circuit-breaker: after N consecutive failed fetches we stop querying
    crt.sh for the rest of the run (once it rate-limits us, every further query
    will too — no point waiting on all of them).
"""
from __future__ import annotations

from typing import Iterable

import httpx

from ..core.collector import Collector
from ..core.fetch import fetch_json
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register
from .certstream import (  # reuse existing keyword filter + TLD harvest config
    ALWAYS_HARVEST_TLDS,
    _has_always_harvest_tld,
    _strip_subdomain_signal,
    domain_matches,
)

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

# TLD-harvest patterns — crt.sh supports wildcard TLD queries (e.g. q=%.ai).
# These mirror certstream's TLD-harvest path: every new domain on these TLDs is
# a discovery candidate, even without an AI keyword in the name. Derived from
# certstream.ALWAYS_HARVEST_TLDS so the list is never duplicated.
HARVEST_PATTERNS = ["%" + tld for tld in ALWAYS_HARVEST_TLDS]

# Subdomain-signal patterns — crt.sh wildcard queries targeting common API /
# commerce subdomains (api.foo.com, console.foo.com, ...). These mirror
# certstream's subdomain-signal path: a cert exposing one of these hosts is
# almost always a developer platform, even without an AI keyword in the name.
# Matches are stripped back to the registrable domain before emission.
SUBDOMAIN_PATTERNS = ["api.%", "console.%", "studio.%", "dashboard.%"]

CRTSH_URL = "https://crt.sh/"

# Stop hitting crt.sh after this many consecutive failed fetches — it's
# rate-limiting us and every further query would just block for the timeout.
MAX_CONSECUTIVE_FAILS = 3


@register
class CrtshCollector(Collector):
    name = "crtsh"
    kind = "http-poll"
    interval = 3600  # once per hour — suitable for CF Cron free tier

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout

    async def collect(self, max_per_pattern: int = 500) -> Iterable[Signal]:
        out: list[Signal] = []
        seen: set[str] = set()
        harvest_count = 0
        self._fails = 0
        self._aborted = False

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": "AiApiRadar/0.1"},
        ) as client:

            async def _query(pattern: str):
                """One crt.sh query with circuit-breaker bookkeeping.

                Returns the parsed JSON list, or None on failure (and trips the
                breaker after MAX_CONSECUTIVE_FAILS consecutive failures).
                """
                data = await fetch_json(CRTSH_URL, params={
                    "q": pattern, "output": "json", "exclude": "expired",
                }, client=client)
                if data is None:
                    self._fails += 1
                    if self._fails >= MAX_CONSECUTIVE_FAILS:
                        self._aborted = True
                        log.warning(
                            "crtsh: %d consecutive failures — rate-limited, "
                            "skipping remaining patterns this run", self._fails,
                        )
                    return None
                self._fails = 0
                return data

            # Path 1: keyword patterns → force_classify (classify immediately).
            for pattern in SEARCH_PATTERNS:
                if self._aborted:
                    break
                data = await _query(pattern)
                if data is None:
                    continue
                rows = 0
                for entry in data:
                    if rows >= max_per_pattern:
                        break
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
                    rows += 1

            # Path 2: TLD-harvest patterns → service_candidate only (no force_classify).
            for pattern in HARVEST_PATTERNS:
                if self._aborted:
                    break
                data = await _query(pattern)
                if data is None:
                    continue
                rows = 0
                for entry in data:
                    if rows >= max_per_pattern:
                        break
                    for name_val in (entry.get("name_value") or "").split("\n"):
                        dom = name_val.strip().lstrip("*.")
                        if not dom or dom in seen:
                            continue
                        if domain_matches(dom):
                            seen.add(dom)
                            out.append(Signal(
                                source=self.name,
                                raw_text=dom,
                                url=f"https://{dom}",
                                source_url=f"https://crt.sh/?q={dom}",
                                meta={"service_candidate": True, "force_classify": True},
                            ))
                        elif _has_always_harvest_tld(dom):
                            seen.add(dom)
                            out.append(Signal(
                                source=self.name,
                                raw_text=dom,
                                url=f"https://{dom}",
                                source_url=f"https://crt.sh/?q={dom}",
                                meta={"service_candidate": True},
                            ))
                            harvest_count += 1
                    rows += 1

            # Path 3: subdomain-signal patterns → service_candidate only.
            for pattern in SUBDOMAIN_PATTERNS:
                if self._aborted:
                    break
                data = await _query(pattern)
                if data is None:
                    continue
                rows = 0
                for entry in data:
                    if rows >= max_per_pattern:
                        break
                    for name_val in (entry.get("name_value") or "").split("\n"):
                        host = name_val.strip().lstrip("*.")
                        if not host:
                            continue
                        dom = _strip_subdomain_signal(host)
                        if dom in seen:
                            continue
                        seen.add(dom)
                        out.append(Signal(
                            source=self.name,
                            raw_text=dom,
                            url=f"https://{dom}",
                            source_url=f"https://crt.sh/?q={dom}",
                            meta={"service_candidate": True},
                        ))
                        harvest_count += 1
                    rows += 1

        log.info(
            "crtsh found %d candidate domains (%d TLD-harvest)%s",
            len(out), harvest_count,
            " [aborted: crt.sh rate-limited]" if self._aborted else "",
        )
        return out

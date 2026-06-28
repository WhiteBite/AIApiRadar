"""CrtshCollector — polls crt.sh API for new AI-related domains.

Alternative to CertStreamCollector for platforms without persistent WebSocket
support (e.g. Cloudflare Workers Cron, GitHub Actions).

Queries crt.sh for certificates matching AI/relay patterns issued recently.
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


@register
class CrtshCollector(Collector):
    name = "crtsh"
    kind = "http-poll"
    interval = 3600  # once per hour — suitable for CF Cron free tier

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout

    async def collect(self, max_per_pattern: int = 500) -> Iterable[Signal]:
        out: list[Signal] = []
        seen: set[str] = set()
        harvest_count = 0
        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": "AiApiRadar/0.1"},
        ) as client:
            # Path 1: keyword patterns → force_classify (classify immediately).
            for pattern in SEARCH_PATTERNS:
                try:
                    data = await fetch_json(CRTSH_URL, params={
                        "q": pattern,
                        "output": "json",
                        "exclude": "expired",
                    }, client=client)
                    if data is None:
                        continue
                    rows = 0
                    for entry in data or []:
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
                except Exception:
                    log.warning("crtsh pattern %s failed", pattern, exc_info=False)

            # Path 2: TLD-harvest patterns → service_candidate only (no force_classify).
            # crt.sh wildcard TLD queries (e.g. %.ai) can return a LOT of rows and
            # can be slow, so each pattern is capped and isolated in try/except.
            for pattern in HARVEST_PATTERNS:
                try:
                    data = await fetch_json(CRTSH_URL, params={
                        "q": pattern,
                        "output": "json",
                        "exclude": "expired",
                    }, client=client)
                    if data is None:
                        continue
                    rows = 0
                    for entry in data or []:
                        if rows >= max_per_pattern:
                            break
                        for name_val in (entry.get("name_value") or "").split("\n"):
                            dom = name_val.strip().lstrip("*.")
                            if not dom or dom in seen:
                                continue
                            if domain_matches(dom):
                                # Keyword match: strong signal, classify immediately.
                                seen.add(dom)
                                out.append(Signal(
                                    source=self.name,
                                    raw_text=dom,
                                    url=f"https://{dom}",
                                    source_url=f"https://crt.sh/?q={dom}",
                                    meta={"service_candidate": True, "force_classify": True},
                                ))
                            elif _has_always_harvest_tld(dom):
                                # TLD-only harvest: brandable name, probe worker decides.
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
                except Exception:
                    log.warning("crtsh pattern %s failed", pattern, exc_info=False)

            # Path 3: subdomain-signal patterns → service_candidate only.
            # crt.sh returns the full SAN host (e.g. api.foobar.com); strip the
            # signal prefix back to the registrable domain so the probe targets
            # the real service, and dedup on the stripped value.
            for pattern in SUBDOMAIN_PATTERNS:
                try:
                    data = await fetch_json(CRTSH_URL, params={
                        "q": pattern,
                        "output": "json",
                        "exclude": "expired",
                    }, client=client)
                    if data is None:
                        continue
                    rows = 0
                    for entry in data or []:
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
                except Exception:
                    log.warning("crtsh pattern %s failed", pattern, exc_info=False)
        log.info(
            "crtsh found %d candidate domains (%d TLD-harvest)",
            len(out), harvest_count,
        )
        return out

"""Wellfound (AngelList) collector — AI startups hiring ML engineers.

A startup posting machine-learning roles is usually building an AI product,
often with a public API/free tier. There's no official free API, so this is a
best-effort scrape of a public role listing page. Correctness of the graceful
no-op (return [] when blocked) matters more than coverage.
"""
from __future__ import annotations

from typing import Iterable
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("wellfound")

LISTING_URL = "https://wellfound.com/role/r/machine-learning-engineer"

_SELF_HOSTS = {
    "wellfound.com", "angel.co", "angellist.com",
    "twitter.com", "x.com", "facebook.com", "linkedin.com", "youtube.com",
}


def _host(url: str) -> str:
    return (urlparse(url).netloc or "").lower().replace("www.", "")


def parse_wellfound(html: str) -> list[Signal]:
    """Pure parse: listing HTML -> Signals. No network."""
    out: list[Signal] = []
    if not html:
        return out
    soup = BeautifulSoup(html, "html.parser")
    base_host = _host(LISTING_URL)
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(LISTING_URL, a["href"])
        if not href.startswith("http"):
            continue
        host = _host(href)
        if not host or host == base_host or host in _SELF_HOSTS:
            continue
        if href in seen:
            continue
        seen.add(href)
        text = " ".join(a.get_text(" ", strip=True).split())
        title = a.get("title") or ""
        company_context = f"{text} {title}".strip()
        if not company_context:
            continue
        out.append(Signal(
            source="wellfound",
            raw_text=company_context[:2000],
            url=href,
            source_url=LISTING_URL,
            meta={"service_candidate": True},
        ))
    return out


@register
class WellfoundCollector(Collector):
    name = "wellfound"
    kind = "scraper"
    interval = 86400

    def __init__(self, listing_url: str = LISTING_URL, timeout: float = 25.0):
        self.listing_url = listing_url
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0 AiApiRadar/0.1"}) as client:
            try:
                resp = await client.get(self.listing_url)
                if resp.status_code == 200:
                    out = parse_wellfound(resp.text)
                else:
                    log.debug("wellfound HTTP %s (likely blocked)", resp.status_code)
            except Exception:
                log.debug("wellfound request failed", exc_info=False)
        log.info("wellfound collected %d candidates", len(out))
        return out

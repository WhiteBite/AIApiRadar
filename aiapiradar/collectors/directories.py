"""AI tool directory collector — theresanaiforthat / futurepedia / toolify.

Legit SaaS self-publish to these directories at launch, often tagged
"Free" / "Free trial". We scrape listing pages, extract outbound tool links
with their surrounding text, and let the classifier judge.
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

log = get_logger("directories")

# Listing pages most likely to surface fresh free-tier tools.
PAGES = {
    "theresanaiforthat": "https://theresanaiforthat.com/just-launched/",
    "futurepedia": "https://www.futurepedia.io/ai-tools?pricing=free_trial",
    "toolify": "https://www.toolify.ai/new",
}

_SELF_HOSTS = {
    "theresanaiforthat.com", "futurepedia.io", "toolify.ai",
    "twitter.com", "x.com", "facebook.com", "linkedin.com", "youtube.com",
}


def _host(url: str) -> str:
    return (urlparse(url).netloc or "").lower().replace("www.", "")


def parse_listing(html_text: str, base_url: str, source: str) -> list[Signal]:
    """Pure parse: HTML listing -> Signals (one per outbound tool link)."""
    soup = BeautifulSoup(html_text, "html.parser")
    base_host = _host(base_url)
    seen: set[str] = set()
    signals: list[Signal] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
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
        raw = f"{text} {title}".strip()
        if not raw:
            continue
        signals.append(Signal(
            source=source,
            raw_text=raw[:2000],
            url=href,
            source_url=base_url,
        ))
    return signals


@register
class DirectoriesCollector(Collector):
    name = "directories"
    kind = "scraper"
    interval = 3600

    def __init__(self, pages: dict[str, str] | None = None, timeout: float = 25.0):
        self.pages = pages or PAGES
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0 AiApiRadar/0.1"}) as client:
            for source, url in self.pages.items():
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    out.extend(parse_listing(resp.text, url, source))
                except Exception:
                    log.warning("directory page failed: %s", source, exc_info=False)
        log.info("directories collected %d links", len(out))
        return out

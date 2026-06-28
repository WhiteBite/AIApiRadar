"""Coupon / deal aggregator collector.

Instead of hardcoding known brands, we scrape AI-category pages on deal
aggregator sites. These pages list *new* tools and promotions, so we discover
services before they reach community channels — without needing to know the
brand name in advance.

The ``parse_coupon`` helper is preserved for backward compatibility (tests
and any downstream callers that supply their own HTML + brand).
"""
from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from ..core.collector import Collector
from ..core.fetch import fetch_text
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("coupon")

_UA = "Mozilla/5.0 AiApiRadar/0.1"

# (source_name, page_url, _reserved).
# Add new aggregators here — the collector needs no other changes.
AGGREGATOR_PAGES = [
    # AppSumo AI tools — limited-time lifetime deals and free trials
    ("appsumo",    "https://appsumo.com/browse/?category=ai",       None),
    # SaaSWorthy AI tools sorted by newest
    ("saasworthy", "https://www.saasworthy.com/category/ai-tools",   None),
    # Futurelist — new AI tool launches
    ("futurelist",  "https://futurelist.co/",                        None),
    # Uneed — product launches with pricing info
    ("uneed",       "https://www.uneed.app/",                        None),
]

_OFFER_RE = re.compile(
    r"(free trial|free credits?|no credit card|freemium|\d+%\s*off|\$\d+|"
    r"trial|lifetime deal|free tier|free plan|promo code|coupon)",
    re.IGNORECASE,
)


def _host(url: str) -> str:
    """Return the netloc of *url*, or an empty string on parse error."""
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _parse_aggregator(html_text: str, agg_name: str, page_url: str) -> list[Signal]:
    """Extract outbound offer-links from an aggregator page.

    For each ``<a href="...">`` that:
    * points to a third-party domain (not the aggregator itself), and
    * whose anchor text or the surrounding element's text matches _OFFER_RE,

    emit one Signal with the linked domain as ``url``.
    """
    own_host = _host(page_url)
    soup = BeautifulSoup(html_text, "html.parser")
    out: list[Signal] = []
    seen: set[str] = set()

    for tag in soup.find_all("a", href=True):
        href: str = tag["href"].strip()
        if not href.startswith("http"):
            continue
        link_host = _host(href)
        if not link_host or link_host == own_host:
            continue  # skip internal / relative links

        # Gather text: anchor text + closest block-level ancestor text
        anchor_text = tag.get_text(strip=True)
        parent = tag.parent
        context_text = parent.get_text(" ", strip=True) if parent else anchor_text
        combined = f"{anchor_text} {context_text}"[:400]

        if not _OFFER_RE.search(combined):
            continue

        # Deduplicate by (agg, linked_host)
        key = (agg_name, link_host)
        if key in seen:
            continue
        seen.add(key)

        linked_domain = f"https://{link_host}"
        raw = combined[:200].strip()
        out.append(Signal(
            source=agg_name,
            raw_text=raw,
            url=linked_domain,
            source_url=page_url,
            meta={"aggregator": agg_name},
        ))

    return out


def parse_coupon(html_text: str, brand_domain: str, source: str, page_url: str) -> list[Signal]:
    """Pure helper: extract an offer snippet for a *known* brand from a coupon page.

    Kept for backward compatibility and direct unit-test use.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    title = (soup.title.get_text(strip=True) if soup.title else "")
    desc_tag = soup.find("meta", attrs={"name": "description"})
    desc = desc_tag.get("content", "") if desc_tag else ""
    body = soup.get_text(" ", strip=True)
    m = _OFFER_RE.search(body)
    snippet = ""
    if m:
        start = max(0, m.start() - 60)
        snippet = body[start:m.end() + 60]
    text = " ".join(f"{title} {desc} {snippet}".split())
    if not _OFFER_RE.search(text):
        return []
    return [Signal(
        source=source,
        raw_text=text[:2000],
        url=f"https://{brand_domain}",
        source_url=page_url,
        meta={"brand": brand_domain},
    )]


@register
class CouponCollector(Collector):
    """Scrape AI deal aggregators for unknown services advertising free offers."""

    name = "coupon"
    kind = "scraper"
    interval = 7200

    def __init__(self, aggregator_pages=None, timeout: float = 25.0):
        self.aggregator_pages = aggregator_pages or AGGREGATOR_PAGES
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        """Fetch each aggregator page and emit Signals for outbound offer links."""
        out: list[Signal] = []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            for agg_name, page_url, _ in self.aggregator_pages:
                text = await fetch_text(page_url, client=client, ua=_UA)
                if text is not None:
                    signals = _parse_aggregator(text, agg_name, page_url)
                    out.extend(signals)
                    log.debug("coupon/%s: %d offers", agg_name, len(signals))
        log.info("coupon collected %d offer links", len(out))
        return out

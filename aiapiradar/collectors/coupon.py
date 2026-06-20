"""Coupon / affiliate aggregator collector.

Established SaaS run promos (referral/coupon/trial) that surface on coupon and
affiliate sites long before community reposts. This covers the gumloop/duet
case that CT-logs and new-domain tricks miss. Configurable (page -> brand).
"""
from __future__ import annotations

import re
from typing import Iterable

import httpx
from bs4 import BeautifulSoup

from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("coupon")

# (source, page_url, brand_domain). Add brands as needed.
TARGETS = [
    ("grabon", "https://www.grabon.in/gumloop-coupons/", "gumloop.com"),
    ("affiliateweapons", "https://affiliateweapons.com/affiliate-tools/duet/", "duet.so"),
]

_OFFER_RE = re.compile(
    r"(free trial|free credits?|no credit card|\d+%\s*off|\$\d+|trial)",
    re.IGNORECASE,
)


def parse_coupon(html_text: str, brand_domain: str, source: str, page_url: str) -> list[Signal]:
    """Pure: extract an offer snippet for a brand if the page mentions one."""
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
    name = "coupon"
    kind = "scraper"
    interval = 7200

    def __init__(self, targets=None, timeout: float = 25.0):
        self.targets = targets or TARGETS
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0 AiApiRadar/0.1"}) as client:
            for source, page_url, brand in self.targets:
                try:
                    r = await client.get(page_url)
                    if r.status_code == 200:
                        out.extend(parse_coupon(r.text, brand, source, page_url))
                except Exception:
                    log.warning("coupon page failed: %s", source, exc_info=False)
        log.info("coupon collected %d brand offers", len(out))
        return out

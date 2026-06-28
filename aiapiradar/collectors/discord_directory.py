"""Discord directory collector — disboard.org AI server listings.

disboard.org publishes public Discord servers by tag. New servers under the
"ai" tag often front a new tool/service; the listing exposes a name,
description, and sometimes a website/invite link. We harvest those into
Signals — a domain in the description may surface downstream even when only an
invite link is present.
"""
from __future__ import annotations

from typing import Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..core.collector import Collector
from ..core.fetch import fetch_text
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("discord_dir")

LISTING_URL = "https://disboard.org/servers/tag/ai"
_UA = "Mozilla/5.0 AiApiRadar/0.1"

_SELF_HOSTS = {
    "disboard.org",
    "twitter.com", "x.com", "facebook.com", "linkedin.com", "youtube.com",
}


def _host(url: str) -> str:
    return (urlparse(url).netloc or "").lower().replace("www.", "")


def _first_external_link(card) -> str | None:
    for a in card.find_all("a", href=True):
        href = urljoin(LISTING_URL, a["href"])
        if not href.startswith("http"):
            continue
        host = _host(href)
        if host and host not in _SELF_HOSTS:
            return href
    return None


def parse_disboard(html: str) -> list[Signal]:
    """Pure parse: disboard listing HTML -> Signals. No network."""
    out: list[Signal] = []
    if not html:
        return out
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".server-card") or soup.find_all(
        "div", class_=lambda c: bool(c) and "server" in c
    )
    seen: set[str] = set()
    for card in cards:
        name_el = card.find(class_=lambda c: bool(c) and "server-name" in c)
        name = " ".join(name_el.get_text(" ", strip=True).split()) if name_el else ""
        desc_el = card.find(class_=lambda c: bool(c) and "server-description" in c)
        description = " ".join(desc_el.get_text(" ", strip=True).split()) if desc_el else ""
        website = _first_external_link(card)
        text = f"{name}. {description}".strip(". ").strip()
        if not text and not website:
            continue
        key = website or text[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(Signal(
            source="discord_dir",
            raw_text=text[:4000],
            url=website,
            source_url=LISTING_URL,
            meta={},
        ))
    return out


@register
class DiscordDirectoryCollector(Collector):
    name = "discord_dir"
    kind = "scraper"
    interval = 43200

    def __init__(self, listing_url: str = LISTING_URL, timeout: float = 25.0):
        self.listing_url = listing_url
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        text = await fetch_text(self.listing_url, timeout=self.timeout, ua=_UA)
        if text is not None:
            out = parse_disboard(text)
        log.info("discord_dir collected %d servers", len(out))
        return out

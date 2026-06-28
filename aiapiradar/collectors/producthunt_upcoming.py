"""Product Hunt "Upcoming"/newest collector — early lead on launches.

Product Hunt's GraphQL API v2 surfaces freshly-posted products before they
trend. We poll the NEWEST posts to catch services 1-3 days ahead of the RSS
feed. Requires a free developer token; without one the collector is a no-op.
"""
from __future__ import annotations

from typing import Iterable

import httpx

from ..config import get_settings
from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("ph_upcoming")

GRAPHQL_URL = "https://api.producthunt.com/v2/api/graphql"

QUERY = """
query {
  posts(order: NEWEST, first: 50) {
    edges {
      node {
        id
        name
        tagline
        url
        website
        topics(first: 5) { edges { node { name } } }
      }
    }
  }
}
"""

# guard so the "no token" notice is logged at most once per process
_warned_no_token = False


def parse_ph(data: dict) -> list[Signal]:
    """Pure parse: GraphQL response dict -> Signals. No network."""
    out: list[Signal] = []
    try:
        edges = data["data"]["posts"]["edges"]
    except (KeyError, TypeError):
        return out
    for edge in edges or []:
        node = (edge or {}).get("node") or {}
        name = (node.get("name") or "").strip()
        tagline = (node.get("tagline") or "").strip()
        website = node.get("website") or None
        url = node.get("url") or None
        topics = []
        try:
            for t in node.get("topics", {}).get("edges", []) or []:
                tn = (t or {}).get("node", {}).get("name")
                if tn:
                    topics.append(tn)
        except (KeyError, TypeError, AttributeError):
            pass
        text = f"{name}. {tagline}".strip(". ").strip()
        if not text and not (website or url):
            continue
        out.append(Signal(
            source="ph_upcoming",
            raw_text=text[:4000],
            url=website or url,
            source_url=url,
            meta={"service_candidate": True, "topics": topics},
        ))
    return out


@register
class ProductHuntUpcomingCollector(Collector):
    name = "ph_upcoming"
    kind = "api"
    interval = 1800

    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        global _warned_no_token
        token = getattr(get_settings(), "ph_token", "") or ""
        if not token:
            if not _warned_no_token:
                log.info("ph_upcoming disabled: no ph_token configured")
                _warned_no_token = True
            return []

        out: list[Signal] = []
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AiApiRadar/0.1",
        }
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True,
                                     headers=headers) as client:
            try:
                resp = await client.post(GRAPHQL_URL, json={"query": QUERY})
                if resp.status_code == 200:
                    out = parse_ph(resp.json())
                else:
                    log.warning("ph_upcoming HTTP %s", resp.status_code)
            except Exception:
                log.warning("ph_upcoming request failed", exc_info=False)
        log.info("ph_upcoming collected %d entries", len(out))
        return out

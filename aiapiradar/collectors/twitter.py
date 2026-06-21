"""X / Twitter collector — promo codes and free-tier launches.

Primary:  Twitter API v2 recent-search  (requires AIRADAR_TW_BEARER_TOKEN)
Fallback: Nitter user-timeline RSS for a curated account list
          (search RSS is disabled on all public instances; timelines still work
          on some — but are unreliable long-term).

WHY THIS MATTERS:
AI startup founders tweet promo codes ("BANDHACK26", "BCFREE") hours before
they reach Telegram aggregator channels. This collector closes that gap.

SETUP (one-time):
1. Go to developer.twitter.com → "Free" tier is enough.
2. Create an app, copy the Bearer Token.
3. Set AIRADAR_TW_BEARER_TOKEN=<token> in your .env

Without a token the collector logs a one-time warning and returns nothing.
"""
from __future__ import annotations

import html
import re
import urllib.parse
from typing import Iterable

import feedparser
import httpx

from ..config import get_settings
from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("twitter")

# ── Twitter v2 API ────────────────────────────────────────────────────────────
TW_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"

# Targeted at promo code / free-tier announcements.
# Using Twitter's exact-phrase / OR operators.
SEARCH_QUERIES = [
    # Promo code pattern: catches "BANDHACK26", "BCFREE", etc.
    '(AI OR LLM OR API) "promo code" free -is:retweet lang:en',
    '(AI OR API) "free credits" signup -is:retweet lang:en',
    '(AI OR API) "free tier" launch -is:retweet lang:en',
    '(AI OR API) "free trial" promo -is:retweet lang:en',
    # Russian promo posts
    'AI API "промокод" бесплатно -is:retweet lang:ru',
]

# ── Nitter fallback (user timeline RSS only — search is dead) ─────────────────
NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.1d4.us",
    "https://xcancel.com",
    "https://lightbrd.com",
]

# Curated list of AI startup / aggregator accounts that post promos.
# Add new services here as they're tracked. Handle only — no @ prefix.
WATCH_ACCOUNTS: list[str] = [
    "OpenRouterAI",
    "getmerlin_in",
    "band_ai",
    # "ZenmuxAI",  — add when account confirmed
]

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", text or "")).strip()


# ── Parser helpers ─────────────────────────────────────────────────────────────

def parse_nitter_feed(content: bytes | str, instance: str = "") -> list[Signal]:
    """Nitter RSS XML → Signals."""
    parsed = feedparser.parse(content)
    out: list[Signal] = []
    for e in parsed.entries:
        title   = _clean(getattr(e, "title", ""))
        summary = _clean(getattr(e, "summary", ""))
        link: str = getattr(e, "link", None) or ""
        # Rewrite nitter link → canonical twitter.com URL for stable dedup
        canonical = link.replace(instance, "https://twitter.com") if (instance and link) else link
        text = f"{title}. {summary}".strip(". ").strip()
        if not text and not link:
            continue
        out.append(Signal(
            source="twitter",
            raw_text=text[:4000],
            source_url=canonical or link or None,
            meta={"via": "nitter", "instance": instance},
        ))
    return out


def parse_v2_response(data: dict) -> list[Signal]:
    """Twitter v2 search response → Signals."""
    out: list[Signal] = []
    for tweet in (data or {}).get("data", []):
        tid  = tweet.get("id", "")
        text = tweet.get("text", "")
        out.append(Signal(
            source="twitter",
            raw_text=text[:4000],
            source_url=f"https://twitter.com/i/web/status/{tid}" if tid else None,
            meta={"via": "v2api", "tweet_id": tid},
        ))
    return out


# ── Nitter helper ─────────────────────────────────────────────────────────────

def _is_rss(content: bytes) -> bool:
    return b"<rss" in content[:600] or b"<feed" in content[:600]


async def _nitter_timeline(
    client: httpx.AsyncClient,
    account: str,
    instances: list[str],
) -> list[Signal]:
    """Fetch one account's timeline RSS, trying instances in order."""
    for instance in instances:
        url = f"{instance}/{account}/rss"
        try:
            r = await client.get(url)
            if r.status_code == 200 and _is_rss(r.content):
                signals = parse_nitter_feed(r.content, instance)
                if signals:
                    return signals
        except Exception:
            continue
    return []


# ── Collector ─────────────────────────────────────────────────────────────────

@register
class TwitterCollector(Collector):
    name = "twitter"
    kind = "api"
    interval = 900  # 15 min — Twitter velocity justifies frequent polling

    def __init__(
        self,
        queries: list[str] | None = None,
        accounts: list[str] | None = None,
        instances: list[str] | None = None,
        timeout: float = 20.0,
    ):
        self.queries   = queries   or SEARCH_QUERIES
        self.accounts  = accounts  or WATCH_ACCOUNTS
        self.instances = instances or NITTER_INSTANCES
        self.timeout   = timeout
        self._warned   = False  # emit no-token warning once per process

    def _bearer(self) -> str | None:
        return getattr(get_settings(), "tw_bearer_token", None) or ""

    def configured(self) -> bool:
        return bool(self._bearer())

    async def _collect_v2(self, client: httpx.AsyncClient) -> list[Signal]:
        """Twitter API v2 recent-search (requires bearer token)."""
        token   = self._bearer()
        headers = {"Authorization": f"Bearer {token}"}
        out: list[Signal] = []

        for query in self.queries:
            try:
                r = await client.get(
                    TW_SEARCH_URL,
                    headers=headers,
                    params={
                        "query":       query,
                        "max_results": 20,
                        "tweet.fields": "created_at,author_id",
                    },
                )
                if r.status_code == 200:
                    out.extend(parse_v2_response(r.json()))
                elif r.status_code == 429:
                    log.warning("twitter v2 rate-limited; backing off")
                    break
                else:
                    log.warning("twitter v2 query failed: %s %s", r.status_code, query[:40])
            except Exception:
                log.warning("twitter v2 request error", exc_info=False)

        log.info("twitter v2 collected %d tweets", len(out))
        return out

    async def _collect_nitter(self, client: httpx.AsyncClient) -> list[Signal]:
        """Nitter user-timeline RSS fallback for curated account list."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml, application/xml, */*",
        }
        # Build a fresh client with browser UA (the outer client uses API UA)
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True, headers=headers
        ) as nitter_client:
            all_signals: list[Signal] = []
            for account in self.accounts:
                signals = await _nitter_timeline(nitter_client, account, self.instances)
                all_signals.extend(signals)
                log.debug("nitter @%s → %d signals", account, len(signals))
        return all_signals

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": "AiApiRadar/0.1"},
        ) as client:
            if self.configured():
                # Official API: full keyword search — catches any promo tweet
                out.extend(await self._collect_v2(client))
            else:
                if not self._warned:
                    log.warning(
                        "Twitter collector: no AIRADAR_TW_BEARER_TOKEN set. "
                        "Keyword search disabled; falling back to curated account timelines. "
                        "Get a free bearer token at developer.twitter.com to enable search."
                    )
                    self._warned = True
                # Nitter fallback: only covers accounts in WATCH_ACCOUNTS
                out.extend(await self._collect_nitter(client))

        log.info("twitter collected %d entries", len(out))
        return out

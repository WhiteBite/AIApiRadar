"""Reddit collector — AI/LLM subreddits where free-credit promos surface.

Reddit is the English-language echo of the Chinese relay scene (usually
1-4 weeks later) but also catches legit SaaS promos and OpenRouter-alternative
threads early. We use the per-subreddit `.rss` feeds (more tolerant of
datacenter IPs than the `.json` API and parseable with feedparser).
"""
from __future__ import annotations

import asyncio
import html
import re
from typing import Iterable

import feedparser
import httpx

from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("reddit")

# Subreddits most likely to surface free AI credits / trial offers.
SUBREDDITS = [
    "LocalLLaMA",
    "SillyTavernAI",
    "ClaudeAI",
    "ChatGPTCoding",
    "artificial",
    "singularity",
    "OpenAI",
]

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", text or "")).strip()


def parse_feed(content: str | bytes, subreddit: str) -> list[Signal]:
    """Pure parse: subreddit RSS -> Signals. No network."""
    parsed = feedparser.parse(content)
    out: list[Signal] = []
    for e in parsed.entries:
        title = _clean(getattr(e, "title", ""))
        summary = _clean(getattr(e, "summary", ""))
        link = getattr(e, "link", None)
        text = f"{title}. {summary}".strip()
        if not text and not link:
            continue
        out.append(Signal(
            source="reddit",
            raw_text=text[:6000],
            source_url=link,
            meta={"subreddit": subreddit},
        ))
    return out


@register
class RedditCollector(Collector):
    name = "reddit"
    kind = "rss"
    interval = 1800

    def __init__(self, subreddits: list[str] | None = None, timeout: float = 20.0):
        self.subreddits = subreddits or SUBREDDITS
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        headers = {"User-Agent": "AiApiRadar/0.1 (+https://aiapiradar.cf.whitebite.ru)"}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True,
                                     headers=headers) as client:
            for i, sub in enumerate(self.subreddits):
                if i:
                    await asyncio.sleep(2.5)  # Reddit rate-limits bursts (429)
                url = f"https://www.reddit.com/r/{sub}/new/.rss?limit=50"
                try:
                    r = await client.get(url)
                    if r.status_code == 200:
                        out.extend(parse_feed(r.content, sub))
                    else:
                        log.warning("reddit r/%s -> %s", sub, r.status_code)
                except Exception:
                    log.warning("reddit feed failed: r/%s", sub, exc_info=False)
        log.info("reddit collected %d entries", len(out))
        return out

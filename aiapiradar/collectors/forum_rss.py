"""Forum RSS collector — nodeseek / linux.do / v2ex / RSSHub-powered feeds.

These Chinese/dev forums are the epicentre for API-relay (中转站) launches.
All expose RSS (directly or via RSSHub), readable without login. We parse
entries into Signals; the pre-filter + classifier decide which are actual
offers.
"""
from __future__ import annotations

import html
import re
from typing import Iterable

import feedparser
import httpx

from ..config import get_settings
from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("forum_rss")


def _rsshub(path: str) -> str:
    """Build a RSSHub URL using configured instance or public fallback."""
    base = get_settings().rsshub_url.rstrip("/")
    return f"{base}{path}"


# Per-feed source name -> RSS URL. Tune endpoints in config later.
FEEDS = {
    # ── Chinese/dev forums — API-relay (中转站) launches ──────────────────
    "nodeseek":   "https://rss.nodeseek.com/",
    "linuxdo":    "https://linux.do/latest.rss",
    "linuxdo_top":"https://linux.do/top.rss",
    "v2ex":       "https://www.v2ex.com/feed/tab/all.xml",
    "hostloc":    "https://hostloc.com/forum.php?mod=rss",

    # ── Launch aggregators — new tools from unknown sources ───────────────
    # Key insight: we don't need to know band.ai or getmerlin.in in advance.
    # When they launch/submit to these platforms, we catch them here.
    "betalist":   "https://betalist.com/feed.xml",
    "hackernews_ai": "https://hnrss.org/newest?q=AI+API+free+trial&points=10",
    "hackernews_show": "https://hnrss.org/show",       # Show HN: new products

    # ── RSSHub-powered Chinese social platforms ───────────────────────────
    # Public instance: https://rsshub.app (rate-limited; use AIRADAR_RSSHUB_URL
    # to point at a self-hosted instance). Feeds are best-effort — failures are
    # logged at DEBUG to avoid noise when the public instance is slow.
    "bilibili_search_api":   _rsshub("/bilibili/search/免费API/0/default"),
    "bilibili_search_relay": _rsshub("/bilibili/search/中转站/0/default"),
    "zhihu_topic_api":       _rsshub("/zhihu/topic/19551298"),  # topic: AI
    "csdn_search":           _rsshub("/csdn/search/免费API"),
    "juejin_tag_ai":         _rsshub("/juejin/tag/AI"),
    "weibo_search":          _rsshub("/weibo/search/topics/免费API"),
    "xiaohongshu_search":    _rsshub("/xiaohongshu/search/免费API"),
    "douyin_search":         _rsshub("/douyin/keyword/免费API"),
    "juejin_tag_llm":        _rsshub("/juejin/tag/LLM"),
    "csdn_search_relay":     _rsshub("/csdn/search/中转站"),
}

_TAG_RE = re.compile(r"<[^>]+>")

# Sources that come from RSSHub — log failures at DEBUG, not WARNING
_RSSHUB_SOURCES = frozenset({
    "bilibili_search_api",
    "bilibili_search_relay",
    "zhihu_topic_api",
    "csdn_search",
    "juejin_tag_ai",
    "weibo_search",
    "xiaohongshu_search",
    "douyin_search",
    "juejin_tag_llm",
    "csdn_search_relay",
})


def _clean(text: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", text or "")).strip()


def parse_feed(content: str | bytes, source: str) -> list[Signal]:
    """Pure parse: feed XML -> Signals. No network."""
    parsed = feedparser.parse(content)
    signals: list[Signal] = []
    for entry in parsed.entries:
        title = _clean(getattr(entry, "title", ""))
        summary = _clean(getattr(entry, "summary", ""))
        link = getattr(entry, "link", None)
        text = f"{title}. {summary}".strip()
        if not text and not link:
            continue
        signals.append(Signal(
            source=source,
            raw_text=text[:8000],
            source_url=link,
            meta={"feed_title": title},
        ))
    return signals


@register
class ForumRssCollector(Collector):
    name = "forum_rss"
    kind = "rss"
    interval = 600

    def __init__(self, feeds: dict[str, str] | None = None, timeout: float = 20.0):
        self.feeds = feeds or FEEDS
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True,
                                     headers={"User-Agent": "AiApiRadar/0.1"}) as client:
            for source, url in self.feeds.items():
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    out.extend(parse_feed(resp.content, source))
                except Exception:
                    if source in _RSSHUB_SOURCES:
                        log.debug("rsshub feed failed: %s", source, exc_info=False)
                    else:
                        log.warning("forum feed failed: %s", source, exc_info=False)
        log.info("forum_rss collected %d entries", len(out))
        return out

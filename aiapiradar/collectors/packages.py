"""Package-registry collector — new AI SDK packages on npm + PyPI (§4.6).

A freshly published "openai-compatible client" or "llm sdk" package is often the
first public artifact of a new service shipping a client library. We watch two
registries:

- npm: the search API for a small AI keyword set. Each hit carries a homepage
  link — emitted as the Signal `url` so the harvest pipeline picks up the domain.
- PyPI: the newest-packages RSS feed, filtered to entries matching an AI keyword
  regex.

Both sources are public (no key) and degrade gracefully on network errors.
"""
from __future__ import annotations

import re
from typing import Iterable

import feedparser
import httpx

from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("packages")

# npm search keywords — small, targeted set.
NPM_KEYWORDS = [
    "ai api",
    "llm client",
    "openai compatible",
    "llm gateway",
    "ai sdk",
    "inference api",
]

NPM_SEARCH = "https://registry.npmjs.org/-/v1/search"
PYPI_RSS = "https://pypi.org/rss/packages.xml"

# Any http(s) URL embedded in free-text (descriptions, summaries).
_URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)


def _extract_urls(*values: str | None) -> list[str]:
    """Collect, de-duplicate (order-preserving) http(s) URLs from given texts."""
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        for match in _URL_RE.findall(value):
            url = match.rstrip(".,);]")
            if url and url not in seen:
                seen.add(url)
                out.append(url)
    return out

# Keyword regex used to keep relevant PyPI entries (title/description match).
_AI_KEYWORD_RE = re.compile(
    r"\b(ai|llm|gpt|openai|anthropic|claude|gemini|chatbot|"
    r"embeddings?|completand?ions?|inference)\b",
    re.IGNORECASE,
)


def parse_npm(data: dict, source: str = "npm") -> list[Signal]:
    """Pure parse: npm search response -> Signals. No network.

    For each package we surface every domain we can find: the homepage and
    repository links plus any http(s) URL embedded in the description. A
    separate Signal is emitted per discovered URL so the harvest pipeline picks
    up each domain; packages with no URL still emit one text-only Signal.
    """
    out: list[Signal] = []
    for obj in (data or {}).get("objects", []):
        pkg = obj.get("package") or {}
        name = pkg.get("name") or ""
        if not name:
            continue
        description = pkg.get("description") or ""
        links = pkg.get("links") or {}
        homepage = links.get("homepage")
        repository = links.get("repository")
        urls = _extract_urls(homepage, repository, description)
        text = f"{name}. {description}".strip()[:2000]
        if urls:
            for url in urls:
                out.append(Signal(
                    source=source,
                    raw_text=text,
                    url=url,
                    meta={"package": name, "registry": "npm"},
                ))
        else:
            out.append(Signal(
                source=source,
                raw_text=text,
                url=None,
                meta={"package": name, "registry": "npm"},
            ))
    return out


def parse_pypi_feed(content: str | bytes, source: str = "pypi") -> list[Signal]:
    """Pure parse: PyPI newest-packages RSS -> Signals, AI-filtered. No network."""
    parsed = feedparser.parse(content)
    out: list[Signal] = []
    for entry in parsed.entries:
        title = getattr(entry, "title", "") or ""
        summary = getattr(entry, "summary", "") or ""
        link = getattr(entry, "link", None)
        if not _AI_KEYWORD_RE.search(f"{title} {summary}"):
            continue
        # Prefer the explicit RSS link; fall back to the first <links> href.
        if not link:
            for ref in getattr(entry, "links", []) or []:
                href = ref.get("href") if isinstance(ref, dict) else None
                if href:
                    link = href
                    break
        text = f"{title}. {summary}".strip()
        out.append(Signal(
            source=source,
            raw_text=text[:2000],
            url=link,
            source_url=link,
            meta={"registry": "pypi"},
        ))
    return out


@register
class PackagesCollector(Collector):
    name = "packages"
    kind = "api"
    interval = 21600  # 6h

    def __init__(self, npm_keywords: list[str] | None = None, timeout: float = 25.0):
        self.npm_keywords = npm_keywords or NPM_KEYWORDS
        self.timeout = timeout

    async def _collect_npm(self, client: httpx.AsyncClient) -> list[Signal]:
        out: list[Signal] = []
        for kw in self.npm_keywords:
            try:
                r = await client.get(NPM_SEARCH, params={"text": kw, "size": 20})
                if r.status_code == 200:
                    out.extend(parse_npm(r.json()))
                else:
                    log.warning("npm search %r -> %s", kw, r.status_code)
            except Exception:
                log.warning("npm search failed: %r", kw, exc_info=False)
        return out

    async def _collect_pypi(self, client: httpx.AsyncClient) -> list[Signal]:
        try:
            r = await client.get(PYPI_RSS)
            if r.status_code == 200:
                return parse_pypi_feed(r.content)
            log.warning("pypi rss -> %s", r.status_code)
        except Exception:
            log.warning("pypi rss failed", exc_info=False)
        return []

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        headers = {"User-Agent": "AiApiRadar/0.1"}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True,
                                     headers=headers) as client:
            out.extend(await self._collect_npm(client))
            out.extend(await self._collect_pypi(client))
        log.info("packages collected %d entries", len(out))
        return out

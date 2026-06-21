"""GitHub awesome-list collector — curated relay / free-API tables.

The relay (中转站) and free-AI communities maintain README tables listing live
services with their bonuses. These are pre-filtered goldmines. We pull each
repo's README via the API (default branch, optional token) and emit one Signal
per line that contains an outbound link; the classifier judges each.
"""
from __future__ import annotations

import base64
import re
from typing import Iterable
from urllib.parse import urlparse

import httpx

from ..config import get_settings
from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("github_lists")

# (source_key, "owner/repo"). Missing repos degrade gracefully (logged + skipped).
REPOS = [
    ("ghlist_gptfree", "chatanywhere/GPT_API_free"),
    ("ghlist_aiproxy", "wll8/ai-proxy"),
    ("ghlist_awesomeproxy", "mn-api/awesome-ai-proxy"),
    ("ghlist_freeai", "CyYxl2024/freeai"),
    ("ghlist_freeaitools", "ShaikhWarsi/free-ai-tools"),
]

_URL_RE = re.compile(r"https?://[^\s)\]>\"']+")
_SKIP_HOSTS = {
    "github.com", "raw.githubusercontent.com", "githubusercontent.com",
    "shields.io", "img.shields.io", "camo.githubusercontent.com",
    "badgen.net", "opencollective.com", "ko-fi.com", "patreon.com",
    "t.me", "twitter.com", "x.com", "youtube.com", "youtu.be",
}


def _host(url: str) -> str:
    return (urlparse(url).netloc or "").lower().replace("www.", "")


def parse_readme(text: str, source: str) -> list[Signal]:
    """Pure: README markdown -> Signals (one per line carrying an outbound link)."""
    out: list[Signal] = []
    seen: set[str] = set()
    for line in text.splitlines():
        urls = _URL_RE.findall(line)
        if not urls:
            continue
        ext = next((u for u in urls if _host(u) and _host(u) not in _SKIP_HOSTS), None)
        if not ext:
            continue
        # strip markdown noise for readable context
        ctx = re.sub(r"[|#*`>\[\]]", " ", line)
        ctx = " ".join(ctx.split())
        key = _host(ext)
        if key in seen:
            continue
        seen.add(key)
        out.append(Signal(
            source=source,
            raw_text=ctx[:1000],
            url=ext.rstrip(".,);"),
            source_url=f"https://github.com/{source}",
        ))
    return out


@register
class GitHubListsCollector(Collector):
    name = "github_lists"
    kind = "api"
    interval = 7200

    def __init__(self, repos: list[tuple[str, str]] | None = None, timeout: float = 25.0):
        self.repos = repos or REPOS
        self.timeout = timeout

    def _headers(self) -> dict:
        h = {"Accept": "application/vnd.github+json", "User-Agent": "AiApiRadar/0.1"}
        token = get_settings().github_token
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        async with httpx.AsyncClient(timeout=self.timeout, headers=self._headers()) as client:
            for source, repo in self.repos:
                try:
                    r = await client.get(f"https://api.github.com/repos/{repo}/readme")
                    if r.status_code != 200:
                        log.warning("readme %s -> %s", repo, r.status_code)
                        continue
                    content = r.json().get("content", "")
                    text = base64.b64decode(content).decode("utf-8", "replace")
                    out.extend(parse_readme(text, source))
                except Exception:
                    log.warning("github_lists repo failed: %s", repo, exc_info=False)
        log.info("github_lists collected %d links", len(out))
        return out

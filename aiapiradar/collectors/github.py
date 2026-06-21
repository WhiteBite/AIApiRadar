"""GitHub collector — repos/gists advertising free AI credits.

We proved the value: the agentrouter "$200 free credits" review gist was on
GitHub ~2 months before the Telegram posts. We search repositories (and could
extend to gists/code) for offer phrasing. Uses an optional token for higher
rate limits.
"""
from __future__ import annotations

from typing import Iterable

import httpx

from ..config import get_settings
from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("github")

QUERIES = [
    '"free credits" (claude OR gpt OR gemini) api in:name,description,readme',
    '"free api" key signup credits',
    'new-api OR one-api free credits register',
    'sub2api OR CLIProxyAPI 注册送 OR "free credits"',
    '中转站 注册送 api in:name,description,readme',
    'awesome ai proxy relay 中转站 in:name,description',
]


def parse_search(data: dict, source: str = "github") -> list[Signal]:
    out: list[Signal] = []
    for item in (data or {}).get("items", []):
        name = item.get("full_name") or item.get("name") or ""
        desc = item.get("description") or ""
        home = item.get("homepage") or ""
        html_url = item.get("html_url")
        text = f"{name}. {desc}".strip()
        if not text or (not desc and not home):
            continue
        out.append(Signal(
            source=source,
            raw_text=text[:2000],
            url=home or None,
            source_url=html_url,
            meta={"stars": item.get("stargazers_count")},
        ))
    return out


@register
class GitHubCollector(Collector):
    name = "github"
    kind = "api"
    interval = 3600

    def __init__(self, queries: list[str] | None = None, timeout: float = 25.0):
        self.queries = queries or QUERIES
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
            for q in self.queries:
                try:
                    r = await client.get(
                        "https://api.github.com/search/repositories",
                        params={"q": q, "sort": "updated", "order": "desc", "per_page": 30},
                    )
                    if r.status_code == 200:
                        out.extend(parse_search(r.json()))
                    else:
                        log.warning("github search %s -> %s", q[:30], r.status_code)
                except Exception:
                    log.warning("github query failed", exc_info=False)
        log.info("github collected %d items", len(out))
        return out

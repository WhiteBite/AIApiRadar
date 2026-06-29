"""GitHub collector — repos/gists advertising free AI credits.

We proved the value: the agentrouter "$200 free credits" review gist was on
GitHub ~2 months before the Telegram posts. We search repositories (and could
extend to gists/code) for offer phrasing. Uses an optional token for higher
rate limits.

Two search paths:
* Repository search (search/repositories) — runs without a token, rate-limit 30 req/h.
* Code search (search/code) — requires a token, rate-limit 10 req/min.
  Searches for relay/gateway base_url patterns that appear in code before
  any forum post.
"""
from __future__ import annotations

import asyncio
import re
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
    # relay-specific
    'new-api one-api "free" stars:>5 pushed:>2024-01-01',
    'awesome-free-chatgpt OR awesome-free-api in:name,description',
    '"中转" api relay "注册" stars:>3',
]

# Code search queries targeting relay/gateway base_url patterns.
# These fire only when a GitHub token is available. Kept lean (3 queries) to
# stay fast under the 10 req/min code-search rate limit.
CODE_QUERIES = [
    # OpenAI-compatible base_url pointing at non-official hosts
    'base_url="https://" extension:py extension:js extension:ts -user:openai -user:anthropic',
    'OPENAI_BASE_URL extension:env extension:yaml extension:yml -path:*.lock',
    # new-api / one-api operators posting their deployment URLs in docs
    '"new-api" base_url in:file extension:md extension:txt',
]

# Relay-engine repos where operators post their deployment URLs in issues.
RELAY_REPOS = [
    "Calcium-Ion/new-api",
    "songquanpeng/one-api",
    "sub2api/sub2api",
]

# Terms that pull issues with deployment URLs. Combined into ONE OR-query per
# repo (instead of one request per term) to cut serial wall-time in CI.
ISSUES_QUERIES = [
    "my deployment",
    "my url",
    "my server",
    "部署",        # "deployment" in Chinese
    "我的域名",    # "my domain" in Chinese
    "base_url",
]

# Regex to extract https:// URLs from code fragments.
_URL_RE = re.compile(r'https?://[^\s\'"<>)\]]+')


def parse_search(data: dict, source: str = "github") -> list[Signal]:
    """Parse a GitHub repository search response into Signals."""
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


def _extract_urls(fragment: str) -> list[str]:
    """Return all https URLs found in a text-match fragment."""
    return _URL_RE.findall(fragment or "")


@register
class GitHubCollector(Collector):
    """Collect Signals from GitHub repository search and code search."""

    name = "github"
    kind = "api"
    interval = 3600

    def __init__(self, queries: list[str] | None = None, timeout: float = 15.0):
        self.queries = queries or QUERIES
        self.timeout = timeout

    def _headers(self) -> dict:
        h = {"Accept": "application/vnd.github+json", "User-Agent": "AiApiRadar/0.1"}
        token = get_settings().github_token
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    def _code_headers(self) -> dict:
        """Headers for code search — requests text-match fragments."""
        h = self._headers()
        h["Accept"] = "application/vnd.github.text-match+json"
        return h

    async def _code_search(self, client: httpx.AsyncClient) -> list[Signal]:
        """Search GitHub code for relay/gateway base_url patterns.

        Silently skipped when no GitHub token is configured (code search
        requires authentication). Sleeps 7 s between queries to stay inside
        the 10 req/min rate limit.
        """
        if not get_settings().github_token:
            log.debug("github_code: no token, skipping code search")
            return []

        out: list[Signal] = []
        code_client = client  # reuse session but override headers per-request
        for idx, q in enumerate(CODE_QUERIES):
            if idx > 0:
                await asyncio.sleep(7)  # 10 req/min → ≥6 s gap; use 7 for safety
            try:
                r = await code_client.get(
                    "https://api.github.com/search/code",
                    params={"q": q, "per_page": 30},
                    headers=self._code_headers(),
                )
                if r.status_code != 200:
                    log.warning("github_code search %s -> %s", q[:40], r.status_code)
                    continue
                data = r.json()
                for item in data.get("items", []):
                    html_url = item.get("html_url")
                    for tm in item.get("text_matches", []):
                        fragment = tm.get("fragment", "")
                        if not fragment:
                            continue
                        urls = _extract_urls(fragment)
                        # Emit one Signal per extracted URL (or one without URL).
                        if urls:
                            for url in urls:
                                out.append(Signal(
                                    source="github_code",
                                    raw_text=fragment[:2000],
                                    url=url,
                                    source_url=html_url,
                                ))
                        else:
                            out.append(Signal(
                                source="github_code",
                                raw_text=fragment[:2000],
                                url=None,
                                source_url=html_url,
                            ))
            except Exception:
                log.warning("github_code query failed: %s", q[:40], exc_info=False)

        log.info("github_code collected %d items", len(out))
        return out

    async def _issues_search(self, client: httpx.AsyncClient) -> list[Signal]:
        """Search issues on known relay-engine repos for operator deployment URLs.

        Operators frequently open issues on new-api / one-api repos and paste
        their own deployment URL in the body — this surfaces those domains before
        any forum post. Silently skipped when no GitHub token is configured.
        Uses one combined OR-query per repo (3 requests), 2 s apart, to share
        the token quota with code search without serial blow-up.
        """
        if not get_settings().github_token:
            log.debug("github_issues: no token, skipping issues search")
            return []

        OFFER_KEYWORDS = ("free", "注册", "trial", "免费")
        out: list[Signal] = []
        # One OR-query per repo (was: one request per term) — 3 requests total.
        combined = " OR ".join(ISSUES_QUERIES)

        for repo in RELAY_REPOS:
            await asyncio.sleep(2)
            try:
                r = await client.get(
                    "https://api.github.com/search/issues",
                    params={
                        "q": f"{combined} repo:{repo}",
                        "sort": "created",
                        "order": "desc",
                        "per_page": 30,
                    },
                    headers=self._headers(),
                )
                if r.status_code != 200:
                    log.debug(
                        "github_issues search %s -> %s", repo, r.status_code,
                    )
                    continue
                data = r.json()
                for issue in data.get("items", []):
                    title = issue.get("title") or ""
                    body = (issue.get("body") or "")[:2000]
                    html_url = issue.get("html_url")
                    combined_text = title + " " + body
                    urls = _URL_RE.findall(body)
                    if urls:
                        body_snippet = body[:500]
                        for url in urls:
                            out.append(Signal(
                                source="github_issues",
                                raw_text=(title + ". " + body_snippet)[:2000],
                                url=url,
                                source_url=html_url,
                            ))
                    elif any(kw in combined_text for kw in OFFER_KEYWORDS):
                        out.append(Signal(
                            source="github_issues",
                            raw_text=(title + ". " + body)[:2000],
                            url=None,
                            source_url=html_url,
                        ))
            except Exception:
                log.debug(
                    "github_issues query failed: repo=%s", repo, exc_info=False,
                )

        log.info("github_issues collected %d items", len(out))
        return out

    async def collect(self) -> Iterable[Signal]:
        """Run repository search then code search, return combined Signals."""
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

            # Code search (token-gated, rate-limited internally)
            out.extend(await self._code_search(client))

            # Issues search (token-gated, rate-limited internally)
            out.extend(await self._issues_search(client))

        log.info("github collected %d items total", len(out))
        return out

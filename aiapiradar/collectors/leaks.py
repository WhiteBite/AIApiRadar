"""Leak monitor — GitHub Gists and Pastebin public pastes (§8.4 leak path).

Finds relay domains that were never announced publicly: someone leaked a
working config (base_url + sk- key) in a gist or paste.

SAFETY RULE: We extract ONLY the domain/host from any URL. API keys (sk-,
Bearer tokens, anything matching _KEY_RE) are IMMEDIATELY discarded — never
stored, never logged, never used to verify access. Violating this turns the
collector into a credential harvester, which is both unethical and illegal.
"""
from __future__ import annotations

import asyncio
import re
from typing import Iterable

import feedparser
import httpx

from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("leaks")

# ---------------------------------------------------------------------------
# Safety regexes — used to scrub credential lines BEFORE URL extraction.
# ---------------------------------------------------------------------------

# Patterns that indicate a line contains a credential. Any line matching this
# is dropped entirely before we do any URL or domain extraction.
_KEY_RE = re.compile(
    r"(sk-[A-Za-z0-9\-_]{10,}|Bearer\s+[A-Za-z0-9\-_\.]{10,}|"
    r"api[_-]?key\s*[=:]\s*\S{10,}|Authorization\s*[=:]\s*\S{10,})",
    re.IGNORECASE,
)

# URL pattern — we keep only the host part (group 1).
_URL_RE = re.compile(r"https?://([^\s\"'<>)\]/:]+)")

# Hosts we deliberately ignore — official providers and infrastructure.
_SKIP_HOSTS: frozenset[str] = frozenset({
    "openai.com",
    "api.openai.com",
    "anthropic.com",
    "google.com",
    "googleapis.com",
    "huggingface.co",
    "github.com",
    "pastebin.com",
    "gist.github.com",
    "raw.githubusercontent.com",
    "localhost",
    "example.com",
    "127.0.0.1",
})

# ---------------------------------------------------------------------------
# Paste/gist content filtering
# ---------------------------------------------------------------------------

# Trigger regex for Pastebin titles/summaries — keeps only AI/relay-related pastes.
_AI_PASTE_RE = re.compile(
    r"\b(openai|base_url|llm|claude|chatgpt|gemini|relay|中转|api.key|sk-)\b",
    re.IGNORECASE,
)

# File extensions and description keywords for gist screening.
_GIST_EXTENSIONS = {".env", ".yaml", ".yml", ".txt", ".py", ".js", ".ts"}
_GIST_KEYWORDS = ("base_url", "openai", "api", "llm", "relay", "中转")

# Gist + Pastebin endpoints.
GITHUB_GISTS_URL = "https://api.github.com/gists/public"
PASTEBIN_RSS_URL = "https://pastebin.com/archive/rss"

# Max bytes we read from any single raw paste/gist file.
_MAX_CONTENT = 4000


# ---------------------------------------------------------------------------
# Pure helper — no network, no DB
# ---------------------------------------------------------------------------

def _extract_safe_domains(text: str) -> list[str]:
    """Return relay-candidate domains found in *text*, credentials scrubbed.

    Pure function: no network calls, no side effects.

    Lines that contain credential patterns (_KEY_RE) are dropped wholesale
    before URL extraction — we never see, store, or log the key values.
    """
    # Drop lines with any key pattern first.
    clean_lines = [
        line for line in text.splitlines()
        if not _KEY_RE.search(line)
    ]
    clean = "\n".join(clean_lines)

    # Extract host portions only; deduplicate, preserve order.
    domains: list[str] = []
    for m in _URL_RE.finditer(clean):
        host = m.group(1).lower().strip("./")
        if host and host not in _SKIP_HOSTS and "." in host and host not in domains:
            domains.append(host)
    return domains


# ---------------------------------------------------------------------------
# Gist collection
# ---------------------------------------------------------------------------

def _gist_file_relevant(filename: str, description: str) -> bool:
    """True if this gist file is worth fetching."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _GIST_EXTENSIONS:
        return False
    combined = (filename + " " + description).lower()
    return any(kw in combined for kw in _GIST_KEYWORDS)


async def _collect_gists(
    client: httpx.AsyncClient,
    token: str,
) -> list[Signal]:
    """Fetch latest public gists and emit relay-domain Signals."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    try:
        r = await client.get(
            GITHUB_GISTS_URL,
            params={"per_page": 30},
            headers=headers,
        )
        if r.status_code != 200:
            log.warning("gists list -> %s", r.status_code)
            return []
        gists = r.json()
    except Exception:
        log.warning("gists list fetch failed", exc_info=False)
        return []

    out: list[Signal] = []
    for gist in gists:
        description = (gist.get("description") or "").lower()
        files = gist.get("files") or {}

        for filename, file_meta in files.items():
            if not _gist_file_relevant(filename, description):
                continue

            raw_url = (file_meta or {}).get("raw_url")
            if not raw_url:
                continue

            await asyncio.sleep(1)  # be polite between raw fetches

            try:
                rc = await client.get(raw_url, headers=headers)
                if rc.status_code != 200:
                    log.debug("gist raw fetch %s -> %s", raw_url, rc.status_code)
                    continue
                content = rc.text[:_MAX_CONTENT]
            except Exception:
                log.debug("gist raw fetch failed: %s", raw_url, exc_info=False)
                continue

            domains = _extract_safe_domains(content)
            # content is no longer referenced after this point
            del content

            for domain in domains:
                out.append(Signal(
                    source="gist",
                    raw_text=f"Gist config: {domain}",
                    url=f"https://{domain}",
                    meta={"service_candidate": True},
                ))

    log.info("gists collected %d domain signals", len(out))
    return out


# ---------------------------------------------------------------------------
# Pastebin collection
# ---------------------------------------------------------------------------

def _paste_raw_url(entry_link: str) -> str:
    """Convert a Pastebin view URL to its /raw/ equivalent."""
    # https://pastebin.com/AbCdEfGh  →  https://pastebin.com/raw/AbCdEfGh
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(entry_link)
    path = parsed.path  # e.g. "/AbCdEfGh"
    if not path.startswith("/raw"):
        path = "/raw" + path
    return urlunparse(parsed._replace(path=path))


async def _collect_pastebin(client: httpx.AsyncClient) -> list[Signal]:
    """Fetch Pastebin public RSS and emit relay-domain Signals."""
    try:
        r = await client.get(PASTEBIN_RSS_URL)
        if r.status_code == 429:
            log.warning("pastebin RSS -> 429 (throttled), skipping")
            return []
        if r.status_code != 200:
            log.warning("pastebin RSS -> %s", r.status_code)
            return []
        feed_content = r.content
    except Exception:
        log.warning("pastebin RSS fetch failed", exc_info=False)
        return []

    parsed = feedparser.parse(feed_content)
    out: list[Signal] = []

    for entry in parsed.entries:
        title = getattr(entry, "title", "") or ""
        summary = getattr(entry, "summary", "") or ""
        link = getattr(entry, "link", None) or ""

        if not _AI_PASTE_RE.search(f"{title} {summary}"):
            continue

        raw_url = _paste_raw_url(link) if link else None
        if not raw_url:
            continue

        try:
            rc = await client.get(raw_url)
            if rc.status_code == 429:
                log.warning("pastebin raw -> 429 (throttled), stopping paste fetches")
                break
            if rc.status_code != 200:
                log.debug("pastebin raw %s -> %s", raw_url, rc.status_code)
                continue
            content = rc.text[:_MAX_CONTENT]
        except Exception:
            log.debug("pastebin raw fetch failed: %s", raw_url, exc_info=False)
            continue

        domains = _extract_safe_domains(content)
        del content

        for domain in domains:
            out.append(Signal(
                source="pastebin",
                raw_text=f"Paste config: {domain}",
                url=f"https://{domain}",
                meta={"service_candidate": True},
            ))

    log.info("pastebin collected %d domain signals", len(out))
    return out


# ---------------------------------------------------------------------------
# Collector class
# ---------------------------------------------------------------------------

@register
class LeaksCollector(Collector):
    """Monitors GitHub Gists and Pastebin for leaked relay/API configs."""

    name = "leaks"
    kind = "scraper"
    interval = 3600  # hourly

    def __init__(self, timeout: float = 25.0):
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        from ..config import get_settings

        settings = get_settings()
        github_token = getattr(settings, "github_token", None)

        headers = {"User-Agent": "AiApiRadar/0.1"}
        out: list[Signal] = []

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers=headers,
        ) as client:
            # --- GitHub Gists (key-gated) ---
            if github_token:
                out.extend(await _collect_gists(client, github_token))
            else:
                log.debug(
                    "leaks: no github_token configured — skipping gist collection"
                )

            # --- Pastebin public RSS (no key required) ---
            out.extend(await _collect_pastebin(client))

        log.info("leaks total: %d domain signals", len(out))
        return out

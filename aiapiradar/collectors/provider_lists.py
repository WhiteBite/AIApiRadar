"""Provider-list collector — supported-provider pages of popular LLM SDKs.

LLM SDKs (litellm and friends) maintain "supported providers" docs. When a new
provider gets listed there, that's an early structural signal that a new
service shipped an API. We don't snapshot/diff here — we simply emit every
provider name and outbound domain found on these pages, and let the harvest
pipeline + probe dedup collapse repeats.

All sources are raw GitHub docs — public, no key. Each fetch is guarded so a
single failure never aborts the others.
"""
from __future__ import annotations

import re
from typing import Iterable

import httpx

from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("provider_lists")

PROVIDERS_MD = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "docs/my-website/docs/providers.md"
)
LITELLM_PRICES = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)

_URL_RE = re.compile(r"https?://[^\s)\]\"'>]+", re.IGNORECASE)
# Markdown table/list provider name, e.g. "| Anthropic |" or "- [OpenAI]"
_NAME_RE = re.compile(r"[|\-*]\s*\[?([A-Za-z][A-Za-z0-9 ._/+-]{1,40})\]?")


def _domain(url: str) -> str | None:
    m = re.match(r"https?://([^/]+)", url or "", re.IGNORECASE)
    return m.group(1).lower() if m else None


def parse_providers_md(text: str) -> list[Signal]:
    """Pure parse: providers.md markdown -> Signals (URLs + names). No network."""
    out: list[Signal] = []
    seen: set[str] = set()

    for url in _URL_RE.findall(text or ""):
        url = url.rstrip(".,;")
        dom = _domain(url)
        if not dom or dom in seen:
            continue
        seen.add(dom)
        out.append(Signal(
            source="provider_lists",
            raw_text=f"LLM provider listed: {dom}",
            url=f"https://{dom}",
            meta={"service_candidate": True},
        ))

    for line in (text or "").splitlines():
        m = _NAME_RE.match(line.strip())
        if not m:
            continue
        name = m.group(1).strip()
        # Skip obvious markdown noise / headers.
        low = name.lower()
        if not name or low in seen or low in {"provider", "providers", "model", "models"}:
            continue
        if low.startswith(("http", "---", "===")):
            continue
        seen.add(low)
        out.append(Signal(
            source="provider_lists",
            raw_text=f"LLM provider listed: {name}",
            url=None,
            meta={"service_candidate": True},
        ))
    return out


def parse_litellm_prices(data: dict) -> list[Signal]:
    """Pure parse: litellm prices JSON -> provider Signals. No network."""
    out: list[Signal] = []
    seen: set[str] = set()
    for key, val in (data or {}).items():
        if key == "sample_spec":
            continue
        providers: list[str] = []
        if isinstance(key, str) and "/" in key:
            providers.append(key.split("/", 1)[0])
        if isinstance(val, dict):
            lp = val.get("litellm_provider")
            if lp:
                providers.append(str(lp))
        for name in providers:
            name = name.strip()
            low = name.lower()
            if not name or low in seen:
                continue
            seen.add(low)
            out.append(Signal(
                source="provider_lists",
                raw_text=f"LLM provider listed: {name}",
                url=None,
                meta={"service_candidate": True},
            ))
    return out


@register
class ProviderListsCollector(Collector):
    name = "provider_lists"
    kind = "api"
    interval = 43200  # 12h

    def __init__(self, timeout: float = 25.0):
        self.timeout = timeout

    async def _fetch_md(self, client: httpx.AsyncClient) -> list[Signal]:
        try:
            r = await client.get(PROVIDERS_MD)
            if r.status_code == 200:
                return parse_providers_md(r.text)
            log.warning("providers.md -> %s", r.status_code)
        except Exception:
            log.warning("providers.md fetch failed", exc_info=False)
        return []

    async def _fetch_prices(self, client: httpx.AsyncClient) -> list[Signal]:
        try:
            r = await client.get(LITELLM_PRICES)
            if r.status_code == 200:
                return parse_litellm_prices(r.json())
            log.warning("litellm prices -> %s", r.status_code)
        except Exception:
            log.warning("litellm prices fetch failed", exc_info=False)
        return []

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        headers = {"User-Agent": "AiApiRadar/0.1"}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True,
                                     headers=headers) as client:
            out.extend(await self._fetch_md(client))
            out.extend(await self._fetch_prices(client))
        log.info("provider_lists collected %d entries", len(out))
        return out

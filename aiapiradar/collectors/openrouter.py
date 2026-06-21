"""OpenRouter collector — structural discovery of new providers/models (§4.5).

OpenRouter aggregates dozens of LLM providers behind one OpenAI-compatible API.
Its public model catalogue is the cleanest structural signal for "a new provider
or model just appeared": every model id carries a provider prefix
(e.g. `deepseek/deepseek-chat`, `mistralai/mistral-7b`). When a new prefix shows
up, that's a new provider worth investigating.

Public endpoint — no key required. We emit one Signal per model so the pipeline
classifier can decide whether the underlying provider is offering free access.
"""
from __future__ import annotations

from typing import Iterable

import httpx

from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("openrouter")

API = "https://openrouter.ai/api/v1/models"


def parse_models(data: dict) -> list[Signal]:
    """Pure parse: OpenRouter `{data:[{id, name, ...}]}` -> Signals. No network."""
    out: list[Signal] = []
    for m in (data or {}).get("data", []):
        mid = m.get("id") or ""
        if not mid:
            continue
        name = m.get("name") or mid
        provider = mid.split("/", 1)[0] if "/" in mid else ""
        out.append(Signal(
            source="openrouter",
            raw_text=f"{name} ({mid})",
            meta={
                "model_id": mid,
                "provider": provider or None,
                "model_release": True,
            },
        ))
    return out


@register
class OpenRouterCollector(Collector):
    name = "openrouter"
    kind = "api"
    interval = 21600  # 6h — the catalogue changes slowly

    def __init__(self, timeout: float = 25.0):
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        headers = {"User-Agent": "AiApiRadar/0.1"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
                r = await client.get(API)
                if r.status_code == 200:
                    out = parse_models(r.json())
                else:
                    log.warning("openrouter models -> %s", r.status_code)
        except Exception:
            log.warning("openrouter collect failed", exc_info=False)
        log.info("openrouter collected %d models", len(out))
        return out

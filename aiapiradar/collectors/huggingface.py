"""Hugging Face collector — new model releases from key orgs.

A new model (e.g. GLM-5.2 from zai-org) is itself a high-signal event that
often precedes credit promos. We watch newest models from major orgs and emit
model_release signals (handled specially in store.persist).
"""
from __future__ import annotations

from typing import Iterable

import httpx

from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("huggingface")

KEY_ORGS = {
    "thudm", "zai-org", "qwen", "deepseek-ai", "mistralai", "meta-llama",
    "google", "openai", "anthropic", "01-ai", "internlm",
}

API = "https://huggingface.co/api/models"


def parse_models(data: list[dict], orgs: set[str] | None = None) -> list[Signal]:
    orgs = orgs or KEY_ORGS
    out: list[Signal] = []
    for m in data or []:
        mid = m.get("id") or m.get("modelId") or ""
        if "/" not in mid:
            continue
        org = mid.split("/", 1)[0].lower()
        if org not in orgs:
            continue
        out.append(Signal(
            source="huggingface",
            raw_text=f"New model release: {mid}",
            url=f"https://huggingface.co/{mid}",
            source_url=f"https://huggingface.co/{mid}",
            meta={"model_release": True, "force_classify": True, "org": org, "model_id": mid},
        ))
    return out


@register
class HuggingFaceCollector(Collector):
    name = "huggingface"
    kind = "api"
    interval = 900

    def __init__(self, limit: int = 100, timeout: float = 25.0):
        self.limit = limit
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        async with httpx.AsyncClient(timeout=self.timeout,
                                     headers={"User-Agent": "AiApiRadar/0.1"}) as client:
            try:
                r = await client.get(API, params={
                    "sort": "createdAt", "direction": -1, "limit": self.limit,
                })
                if r.status_code == 200:
                    out = parse_models(r.json())
            except Exception:
                log.warning("huggingface fetch failed", exc_info=False)
        log.info("huggingface collected %d key-org models", len(out))
        return out

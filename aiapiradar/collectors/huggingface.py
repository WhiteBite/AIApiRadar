"""Hugging Face collector — new model releases from key orgs.

A new model (e.g. GLM-5.2 from zai-org) is itself a high-signal event.
We also detect when a model is live on the HF Inference API — free with any
HF token via an OpenAI-compatible endpoint — and surface that as an offer.

BUG FIX (2025-06): The old approach used `sort=createdAt&limit=100` on the
global models feed. That returns 100 random user fine-tunes and never yields
key-org models (who publish infrequently). The fix: query per org using
`author={org}`, then fetch each model's full record to get the `inference`
field (not present in the list response, only in the individual endpoint).
"""
from __future__ import annotations

import asyncio
from typing import Iterable

import httpx

from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("huggingface")

KEY_ORGS = [
    "thudm", "zai-org", "qwen", "deepseek-ai", "mistralai", "meta-llama",
    "google", "openai", "anthropic", "01-ai", "internlm", "moonshot-ai",
    "stepfun-ai",
]

API = "https://huggingface.co/api/models"

# HF inference states meaning the model is live on the Inference API right now
_LIVE_INFERENCE = {"warm", "loading"}

# How many recent models to inspect per org (keeps extra requests to ~N×LIMIT)
_PER_ORG_LIMIT = 5


def _build_signal_text(mid: str, m: dict) -> str:
    """Build signal text — includes free-API wording when inference is live.

    This matters because:
    - The pipeline prefilter catches "free" / "HF token" keywords.
    - The LLM classifier then marks the signal as is_offer=True.
    - Pure model_release signals (inference=None) bypass the prefilter anyway
      via force_classify=True, but won't be classified as actionable offers.
    """
    inference = (m.get("inference") or "").lower()
    pipeline  = m.get("pipeline_tag") or ""

    base = f"New model release: {mid}"
    if pipeline:
        base += f" ({pipeline})"

    if inference in _LIVE_INFERENCE:
        base += (
            f". Available on HuggingFace Inference API (status={inference}) — "
            "free access with HF token via OpenAI-compatible endpoint. "
            "No registration on third-party services required."
        )

    return base


def parse_models(data: list[dict], org_filter: str | None = None) -> list[Signal]:
    """Convert a list of HF model dicts (with `inference` populated) to Signals."""
    key_set = set(KEY_ORGS)
    out: list[Signal] = []
    for m in data or []:
        mid = m.get("id") or m.get("modelId") or ""
        if "/" not in mid:
            continue
        org = mid.split("/", 1)[0].lower()
        if org_filter and org != org_filter:
            continue
        if not org_filter and org not in key_set:
            continue

        inference = (m.get("inference") or "").lower()
        text = _build_signal_text(mid, m)

        out.append(Signal(
            source="huggingface",
            raw_text=text,
            url=f"https://huggingface.co/{mid}",
            source_url=f"https://huggingface.co/{mid}",
            meta={
                "model_release": True,
                "force_classify": True,
                "org": org,
                "model_id": mid,
                "hf_inference": inference or None,
            },
        ))
    return out


async def _fetch_inference_status(
    client: httpx.AsyncClient, mid: str
) -> str | None:
    """GET /api/models/{mid} and return the `inference` field (or None)."""
    try:
        r = await client.get(f"{API}/{mid}")
        if r.status_code == 200:
            return (r.json().get("inference") or "").lower() or None
    except Exception:
        pass
    return None


@register
class HuggingFaceCollector(Collector):
    name = "huggingface"
    kind = "api"
    interval = 900

    def __init__(
        self,
        orgs: list[str] | None = None,
        per_org_limit: int = _PER_ORG_LIMIT,
        timeout: float = 25.0,
    ):
        self.orgs = orgs or KEY_ORGS
        self.per_org_limit = per_org_limit
        self.timeout = timeout

    async def collect(self) -> Iterable[Signal]:
        out: list[Signal] = []
        headers = {"User-Agent": "AiApiRadar/0.1"}
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            for org in self.orgs:
                try:
                    # Step 1: list recent models for this org
                    r = await client.get(API, params={
                        "author": org,
                        "sort": "lastModified",
                        "direction": -1,
                        "limit": self.per_org_limit,
                    })
                    if r.status_code != 200:
                        log.warning("hf org %s -> %s", org, r.status_code)
                        continue
                    models: list[dict] = r.json()

                    # Step 2: enrich each model with its `inference` status
                    # (field not available in list response, only in /api/models/{id})
                    tasks = [_fetch_inference_status(client, m["id"]) for m in models if m.get("id")]
                    statuses = await asyncio.gather(*tasks)
                    for m, status in zip(models, statuses):
                        m["inference"] = status

                    out.extend(parse_models(models, org_filter=org))

                except Exception:
                    log.warning("huggingface org %s failed", org, exc_info=False)

                # Be gentle: small pause between orgs to avoid bursting
                await asyncio.sleep(0.3)

        live = sum(1 for s in out if s.meta.get("hf_inference") in _LIVE_INFERENCE)
        log.info(
            "huggingface collected %d models from %d orgs (%d on Inference API)",
            len(out), len(self.orgs), live,
        )
        return out

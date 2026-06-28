"""Canonical app-settings defaults — single source of truth for the worker.

`settings_defaults()` assembles the exact shape of the worker's
`SETTINGS_DEFAULTS` from the canonical Python sources (prefilter keyword lists,
scorer constants, and the pydantic `Settings` field defaults). It is consumed by
`scripts/gen_worker_constants.py` to render `worker/src/_generated.ts`.

Values are deterministic: we read the pydantic *field defaults* via
`Settings.model_fields[...].default` rather than instantiating `Settings()` /
`get_settings()`, so the generated worker constants never depend on the dev
machine's `.env`.
"""
from __future__ import annotations


def settings_defaults() -> dict:
    """Return the worker SETTINGS_DEFAULTS shape from canonical Python sources."""
    from .config import Settings
    from .pipeline import prefilter
    from .scorer import EARLY_SIGNAL_BOOST

    f = Settings.model_fields
    return {
        "prefilter_en_strong": list(prefilter.EN_STRONG),
        "prefilter_en_weak": list(prefilter.EN_WEAK),
        "prefilter_ru": list(prefilter.RU_KEYWORDS),
        "prefilter_zh_strong": list(prefilter.ZH_STRONG),
        "prefilter_zh_weak": list(prefilter.ZH_WEAK),
        "score_w_freshness": f["score_w_freshness"].default,
        "score_w_amount": f["score_w_amount"].default,
        "score_w_ease": f["score_w_ease"].default,
        "score_w_reliability": f["score_w_reliability"].default,
        "early_signal_boost": EARLY_SIGNAL_BOOST,
        "discovery_limit": f["discovery_limit"].default,
        "notify_min_score": f["notify_min_score"].default,
    }

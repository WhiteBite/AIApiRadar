"""The Signal — a single raw observation emitted by a collector.

Signals are source-agnostic. The pipeline (normalize -> pre-filter -> classify
-> enrich -> dedup -> store) turns them into Offers attached to Services.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


@dataclass(slots=True)
class Signal:
    source: str                      # collector name, e.g. "certstream", "nodeseek"
    raw_text: str = ""               # human-readable text to classify
    url: Optional[str] = None        # candidate service URL, if known
    source_url: Optional[str] = None # where this signal was observed (post/cert/page)
    lang: Optional[str] = None       # detected language (filled by normalizer)
    observed_at: dt.datetime = field(default_factory=_utcnow)
    meta: dict = field(default_factory=dict)  # collector-specific extras

    def dedup_key(self) -> str:
        """Stable key for early ingestion-level dedup."""
        return f"{self.source}|{self.source_url or self.url or self.raw_text[:120]}"

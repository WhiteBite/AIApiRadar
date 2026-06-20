"""Pipeline orchestrator: normalize -> prefilter -> classify -> store.

Synchronous by design (DB + LLM client are sync). The async scheduler calls it
via asyncio.to_thread, keeping collectors async and the core simple.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable, Optional

from ..core.signal import Signal as RawSignal
from ..db import session_scope
from ..logging_conf import get_logger
from . import normalize, prefilter, store
from .classify import Classification, get_classifier

log = get_logger("pipeline")


class Pipeline:
    def __init__(self, classifier=None, min_confidence: float = 0.4):
        self.classifier = classifier or get_classifier()
        self.min_confidence = min_confidence

    def process_signals(self, signals: Iterable[RawSignal]) -> dict:
        stats: Counter = Counter()
        with session_scope() as session:
            for raw in signals:
                stats["seen"] += 1
                raw, domains = normalize.normalize(raw)

                force = bool(raw.meta.get("force_classify"))
                matched, _ = prefilter.match(raw.raw_text or "")
                if not matched and not force:
                    stats["prefiltered_out"] += 1
                    continue

                clf: Classification = self.classifier.classify(
                    raw.raw_text or "", raw.url, raw.lang or "en", domains
                )
                stats["classified"] += 1
                if clf.is_offer:
                    stats["offers"] += 1

                result = store.persist(session, raw, clf, domains, self.min_confidence)
                for k, v in result.items():
                    stats[k] += v
        log.info("pipeline processed: %s", dict(stats))
        return dict(stats)


_default: Optional[Pipeline] = None


def get_default_pipeline() -> Pipeline:
    global _default
    if _default is None:
        _default = Pipeline()
    return _default


async def async_pipeline(signals: Iterable[RawSignal]) -> None:
    """Async adapter for the scheduler."""
    import asyncio

    pipe = get_default_pipeline()
    await asyncio.to_thread(pipe.process_signals, list(signals))

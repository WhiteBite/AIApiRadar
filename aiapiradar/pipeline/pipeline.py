"""Pipeline orchestrator: normalize -> harvest -> prefilter -> classify -> store.

Synchronous by design (DB + LLM client are sync). The async scheduler calls it
via asyncio.to_thread, keeping collectors async and the core simple.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, Optional

from ..core.signal import Signal as RawSignal
from ..db import get_db
from ..logging_conf import get_logger
from . import normalize, prefilter, store
from .classify import Classification, HeuristicClassifier

log = get_logger("pipeline")

# Domains are harvested for discovery only when the signal text shows some
# AI/offer context. This cuts probe noise (a cooking post on a forum won't
# mention these) while still catching off-hand mentions like
# "btw zenmux.ai has a free trial" that the prefilter/classifier would drop.
# CJK terms sit outside the \b group (no word boundaries in Chinese).
_HARVEST_HINT_RE = re.compile(
    r"\b(ai|llm|api|gpt|claude|gemini|deepseek|qwen|glm|kimi|grok|llama|"
    r"mistral|model|tokens?|credits?|free|trial|promo|voucher|coupon|tier)\b"
    r"|ключ|кредит|бесплат|триал|промокод|额度|免费|注册送|中转",
    re.IGNORECASE,
)

# Bare-domain extractor (no scheme): catches "zenmux.ai" / "getmerlin.in"
# mentioned in plain text, which extract_service_domains (URL-only) misses.
# Restricted to a TLD allow-list so we don't match "node.js", "v2.0", etc.
#
# Improvements over v1:
#  • (?<!@) lookbehind — skips email addresses like user@api.example.ai
#  • Label minimum length ≥3 chars (pattern requires exactly 3+):
#      [a-z0-9]{2}[a-z0-9-]{0,60}[a-z0-9]  → min 2+0+1 = 3 chars
#    This prevents matching "v2.io" (2-char label) or "go.ai" (2-char label).
#  • Extended TLD list: added .top, .pro, .cc (common Chinese relay operators).
_BARE_DOMAIN_RE = re.compile(
    r"(?<!@)\b"
    r"((?:[a-z0-9]{2}[a-z0-9-]{0,60}[a-z0-9]\.)+"
    r"(?:ai|io|com|net|org|dev|app|co|in|xyz|gg|sh|me|cloud|tech|so|chat|run|top|pro|cc))"
    r"\b",
    re.IGNORECASE,
)

# Offer/price trigger keywords for domain-proximity priority boosting.
# When one of these appears within 100 chars of a domain mention, that domain
# gets priority='high' in the probe queue so it's dequeued first.
_OFFER_TRIGGER_NEAR_RE = re.compile(
    r"\b(free|trial|promo|voucher|coupon|credits?|discount|offer|bonus|gift|\$\d)\b"
    r"|注册送|免费|额度|бесплатн|кредит|триал",
    re.IGNORECASE,
)


def _harvest_candidate_domains(raw: RawSignal, url_domains: list[str]) -> list[str]:
    """URL-extracted domains + bare-text domain mentions, deduped."""
    out = list(url_domains)
    for m in _BARE_DOMAIN_RE.findall(raw.raw_text or ""):
        dom = m.lower()
        if dom not in out:
            out.append(dom)
    return out


def _has_offer_near_domain(text: str, domain: str, window: int = 100) -> bool:
    """Return True if an offer/price trigger appears within `window` chars of the domain.

    Used to mark a domain candidate as priority='high' so the probe worker
    processes it before lower-signal mentions.  Case-insensitive, first match wins.
    """
    text_lower = text.lower()
    domain_lower = domain.lower()
    idx = text_lower.find(domain_lower)
    if idx < 0:
        return False
    start = max(0, idx - window)
    end = min(len(text), idx + len(domain) + window)
    return bool(_OFFER_TRIGGER_NEAR_RE.search(text[start:end]))


class Pipeline:
    def __init__(self, classifier=None, min_confidence: float = 0.4):
        # Inline classification runs per-signal across the whole collection
        # stream, so it must be free and quota-free. The heuristic classifier
        # fits that. The LLM is applied separately as a batched enrichment pass
        # (see reclassify.py) on the small set of stored offers, which keeps us
        # within tight free-tier daily request quotas.
        self.classifier = classifier or HeuristicClassifier()
        self.min_confidence = min_confidence

    def process_signals(self, signals: Iterable[RawSignal]) -> dict:
        stats: Counter = Counter()
        with get_db() as db:
            for raw in signals:
                stats["seen"] += 1
                raw, domains = normalize.normalize(raw)

                # Discovery: record every mentioned domain as a candidate BEFORE
                # the prefilter can drop this signal. Decoupling discovery from
                # classification is how we find services we've never heard of —
                # the discovery worker probes these later (see discover.py).
                self._harvest_domains(db, raw, domains, stats)

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

                result = store.persist(db, raw, clf, domains, self.min_confidence)
                for k, v in result.items():
                    stats[k] += v
        log.info("pipeline processed: %s", dict(stats))
        return dict(stats)

    @staticmethod
    def _harvest_domains(db, raw: RawSignal, domains: list[str], stats: Counter) -> None:
        """Queue novel domains mentioned in this signal for later probing."""
        # Gate on AI/offer context to keep the probe queue signal-rich.
        if not _HARVEST_HINT_RE.search(raw.raw_text or ""):
            return
        candidates = _harvest_candidate_domains(raw, domains)
        raw_text = raw.raw_text or ""
        for dom in candidates:
            reg = normalize.registrable_domain(dom)
            if not reg or normalize.is_blocked_domain(reg):
                continue
            # Domains mentioned near a price/offer trigger get priority='high'
            # so the probe worker dequeues them before lower-signal candidates.
            priority = "high" if _has_offer_near_domain(raw_text, dom) else "normal"
            try:
                # UNIQUE(domain) + OR IGNORE = dedup; worker handles known services.
                db.run(
                    "INSERT OR IGNORE INTO domain_candidates (domain, first_source, priority) "
                    "VALUES (?, ?, ?)",
                    [reg, raw.source, priority],
                )
                # If the row already existed but this occurrence has an offer trigger
                # nearby, upgrade its priority so it gets processed sooner.
                if priority == "high":
                    db.run(
                        "UPDATE domain_candidates SET priority='high' "
                        "WHERE domain=? AND priority!='high'",
                        [reg],
                    )
                stats["harvested"] += 1
            except Exception:
                log.debug("harvest insert failed for %s", reg, exc_info=False)


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

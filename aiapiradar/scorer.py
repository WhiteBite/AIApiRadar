"""Offer scoring: freshness x amount x ease x reliability.

score = w_fresh*fresh + w_amount*amount + w_ease*ease + w_reliab*reliability
Weights come from settings (AIRADAR_SCORE_W_*). Result in [0, 1].

rescore_all(db) recomputes scores over the raw-SQL Database path (used by the
watchdog and the scheduler).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from .config import Settings, get_settings
from .db.base import Database
from .logging_conf import get_logger
from .models import utcnow
from .util.dtutil import parse_utc as _dt_parse

log = get_logger("scorer")

# How easy is it to actually claim, by offer type (1.0 = trivial signup).
EASE_BY_TYPE = {
    "saas_trial": 1.0,
    "model_release": 0.9,
    "relay": 0.8,
    "saas_promo": 0.7,
    "grant": 0.6,
    "other": 0.5,
    "abuse": 0.3,
}

# Freshness is the product's core: new offers matter, old ones are dead weight.
# Recency is a multiplicative decay so age dominates ranking regardless of how
# fat the bonus is. Half-life ≈ 2.5 days → ~0.14 after a week, ~0.02 after two.
HALF_LIFE_HOURS = 60.0
# Quality (amount/ease/reliability) only modulates within this band, so a brand
# new mediocre offer still outranks a stale jackpot.
QUALITY_FLOOR = 0.35

# ─── Language-cascade early signal (§8.6) ─────────────────────────────────────
# Relays propagate offers along a language cascade: zh (T+0) → ru (T+1-3d) →
# en (T+3-7d). An offer that shows up in Chinese/Russian chatter but has NOT
# yet surfaced in any English source is EARLY — boosting it puts us ahead of
# the English ecosystem. The boost is additive, conservative, and clamped so
# the total score never exceeds 1.0. It layers on top of the existing
# recency × quality × cross-source score without changing any weight semantics.
EARLY_SIGNAL_BOOST = 0.1

# Fallback collector → language map, used when a signal's `lang` column is
# empty. Only collectors with an unambiguous audience language are listed;
# language-neutral collectors (certstream, crtsh, github, huggingface, …) are
# intentionally absent so they neither trigger nor suppress the early boost.
_SOURCE_LANG = {
    # Chinese-language relays / forums / socials
    "forum_rss": "zh",
    "nodeseek": "zh",
    "linux.do": "zh",
    "bilibili": "zh",
    "csdn": "zh",
    "weibo": "zh",
    # Russian-language channels
    "telegram": "ru",
    "twitter-ru": "ru",
    # English-language sources
    "reddit": "en",
    "hackernews": "en",
    "producthunt": "en",
}


def _norm_lang(value: Optional[str]) -> Optional[str]:
    """Normalize a stored lang code to one of zh/ru/en (or None if other)."""
    if not value:
        return None
    v = str(value).strip().lower()
    if v.startswith("zh"):
        return "zh"
    if v.startswith("ru"):
        return "ru"
    if v.startswith("en"):
        return "en"
    return None


def _signal_lang(source: Optional[str], lang: Optional[str]) -> Optional[str]:
    """Best-effort language for one signal: explicit `lang` wins, else source."""
    return _norm_lang(lang) or _SOURCE_LANG.get((source or "").strip().lower())


def _is_early_signal(langs: set) -> bool:
    """True when an offer has zh and/or ru signals but no en signal yet."""
    return ("en" not in langs) and bool(langs & {"zh", "ru"})


# ─── Pure math helpers ────────────────────────────────────────────────────────

def freshness_score(age_hours: float) -> float:
    """Legacy linear freshness (kept for callers/tests). See recency_decay."""
    if age_hours <= 0:
        return 1.0
    return 1.0 / (1.0 + age_hours / 24.0)


def recency_decay(age_hours: float) -> float:
    """Exponential decay by age. 1.0 now → 0.5 at one half-life → ~0 when stale."""
    if age_hours <= 0:
        return 1.0
    return 0.5 ** (age_hours / HALF_LIFE_HOURS)


def amount_score(amount: Optional[float], cap: float = 200.0) -> float:
    if not amount or amount <= 0:
        return 0.0
    return min(amount / cap, 1.0)


def ease_score(offer_type: str, referral_required: bool) -> float:
    base = EASE_BY_TYPE.get(offer_type, 0.5)
    if referral_required:
        base *= 0.85
    return base


def _quality_blend(amount, offer_type, referral_required, reliability,
                   settings: Settings) -> float:
    """Normalized 'how good is this offer' in [0,1] (amount/ease/reliability)."""
    amt = amount_score(amount)
    ease = ease_score(offer_type, referral_required)
    wsum = (settings.score_w_amount + settings.score_w_ease
            + settings.score_w_reliability) or 1.0
    return (
        settings.score_w_amount * amt
        + settings.score_w_ease * ease
        + settings.score_w_reliability * (reliability or 0.0)
    ) / wsum


def _compose(age_hours: float, quality: float) -> float:
    """Recency dominates; quality modulates within [QUALITY_FLOOR, 1]."""
    decay = recency_decay(age_hours)
    return round(decay * (QUALITY_FLOOR + (1.0 - QUALITY_FLOOR) * quality), 4)


# ─── Database-protocol path ──────────────────────────────────────────────────

def _rescore_all_db(db: Database, settings: Optional[Settings] = None) -> int:
    settings = settings or get_settings()
    now = utcnow()

    rows = db.execute(
        """
        SELECT o.id, o.service_id, o.type, o.amount, o.referral_required,
               o.first_seen_at, COALESCE(s.reliability, 0.0) AS reliability,
               (SELECT COUNT(DISTINCT source) FROM signals WHERE service_id = o.service_id) AS source_count
        FROM offers o
        LEFT JOIN services s ON o.service_id = s.id
        """
    )

    # Batched per-service language set: one scan of `signals` instead of a
    # per-offer subquery. Signals attach to an offer via its service_id (same
    # association the cross-source source_count uses), so we key by service_id.
    lang_by_service: dict = {}
    for sig in db.execute("SELECT service_id, source, lang FROM signals"):
        sid = sig.get("service_id")
        if sid is None:
            continue
        lang = _signal_lang(sig.get("source"), sig.get("lang"))
        if lang:
            lang_by_service.setdefault(sid, set()).add(lang)

    for row in rows:
        first = _dt_parse(row["first_seen_at"]) or now
        if first.tzinfo is None:
            first = first.replace(tzinfo=dt.timezone.utc)
        age_hours = max((now - first).total_seconds() / 3600.0, 0.0)

        quality = _quality_blend(
            row["amount"], row["type"], bool(row["referral_required"]),
            row["reliability"] or 0.0, settings,
        )
        source_count = int(row.get("source_count") or 1)
        boost = 1.0 + 0.15 * min(max(0, source_count - 1), 3)
        # cap at 1.0 so score never exceeds 1
        score = min(round(_compose(age_hours, quality) * boost, 4), 1.0)

        # Language-cascade early-signal boost: zh/ru seen but no en yet.
        # Additive on top of the composed+cross-source score, clamped to 1.0.
        langs = lang_by_service.get(row.get("service_id"), set())
        if _is_early_signal(langs):
            score = min(round(score + EARLY_SIGNAL_BOOST, 4), 1.0)

        db.run("UPDATE offers SET score = ? WHERE id = ?", [score, row["id"]])

    log.info("rescored %d offers (db path)", len(rows))
    return len(rows)


# ─── Public entry point ───────────────────────────────────────────────────────

def rescore_all(db: Database, settings: Optional[Settings] = None) -> int:
    """Recompute scores for every offer over the Database path."""
    return _rescore_all_db(db, settings)

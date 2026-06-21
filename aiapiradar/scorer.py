"""Offer scoring: freshness x amount x ease x reliability.

score = w_fresh*fresh + w_amount*amount + w_ease*ease + w_reliab*reliability
Weights come from settings (AIRADAR_SCORE_W_*). Result in [0, 1].

rescore_all() accepts either:
  - a Database (new protocol path)  — used by watchdog and the scheduler
  - a SQLAlchemy Session            — backward compat for legacy tests
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from .config import Settings, get_settings
from .db.base import Database
from .logging_conf import get_logger
from .models import utcnow

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


def score_offer(offer, service, now: dt.datetime,
                settings: Optional[Settings] = None) -> float:
    """Score an ORM Offer object (backward compat for legacy tests / callers)."""
    settings = settings or get_settings()
    first = offer.first_seen_at or now
    if first.tzinfo is None:
        first = first.replace(tzinfo=dt.timezone.utc)
    age_hours = max((now - first).total_seconds() / 3600.0, 0.0)

    reliab = service.reliability if service else 0.0
    quality = _quality_blend(offer.amount, offer.type, offer.referral_required,
                             reliab, settings)
    return _compose(age_hours, quality)


# ─── Database-protocol path ──────────────────────────────────────────────────

def _dt_parse(s: Optional[str]) -> Optional[dt.datetime]:
    """Parse a stored datetime string → tz-aware UTC datetime."""
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    try:
        d = dt.datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def _rescore_all_db(db: Database, settings: Optional[Settings] = None) -> int:
    settings = settings or get_settings()
    now = utcnow()

    rows = db.execute(
        """
        SELECT o.id, o.type, o.amount, o.referral_required,
               o.first_seen_at, COALESCE(s.reliability, 0.0) AS reliability
        FROM offers o
        LEFT JOIN services s ON o.service_id = s.id
        """
    )

    for row in rows:
        first = _dt_parse(row["first_seen_at"]) or now
        if first.tzinfo is None:
            first = first.replace(tzinfo=dt.timezone.utc)
        age_hours = max((now - first).total_seconds() / 3600.0, 0.0)

        quality = _quality_blend(
            row["amount"], row["type"], bool(row["referral_required"]),
            row["reliability"] or 0.0, settings,
        )
        score = _compose(age_hours, quality)
        db.run("UPDATE offers SET score = ? WHERE id = ?", [score, row["id"]])

    log.info("rescored %d offers (db path)", len(rows))
    return len(rows)


# ─── SQLAlchemy-session path (backward compat) ────────────────────────────────

def _rescore_all_orm(session, settings: Optional[Settings] = None) -> int:
    from sqlalchemy import select

    from .models import Offer, Service

    settings = settings or get_settings()
    now = utcnow()
    offers = session.scalars(select(Offer)).all()
    for offer in offers:
        service = session.get(Service, offer.service_id) if offer.service_id else None
        offer.score = score_offer(offer, service, now, settings)
    log.info("rescored %d offers (orm path)", len(offers))
    return len(offers)


# ─── Public entry point ───────────────────────────────────────────────────────

def rescore_all(session_or_db, settings: Optional[Settings] = None) -> int:
    """Recompute scores for every offer.

    Accepts either a Database (new protocol) or a SQLAlchemy Session (legacy).
    """
    if isinstance(session_or_db, Database):
        return _rescore_all_db(session_or_db, settings)
    return _rescore_all_orm(session_or_db, settings)

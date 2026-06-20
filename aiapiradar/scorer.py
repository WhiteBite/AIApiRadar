"""Offer scoring: freshness x amount x ease x reliability.

score = w_fresh*fresh + w_amount*amount + w_ease*ease + w_reliab*reliability
Weights come from settings (AIRADAR_SCORE_W_*). Result in [0, 1].
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import select

from .config import Settings, get_settings
from .logging_conf import get_logger
from .models import Offer, Service, utcnow

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


def freshness_score(age_hours: float) -> float:
    if age_hours <= 0:
        return 1.0
    return 1.0 / (1.0 + age_hours / 24.0)  # 1.0 now, 0.5 at 24h, 0.25 at 72h


def amount_score(amount: Optional[float], cap: float = 200.0) -> float:
    if not amount or amount <= 0:
        return 0.0
    return min(amount / cap, 1.0)


def ease_score(offer_type: str, referral_required: bool) -> float:
    base = EASE_BY_TYPE.get(offer_type, 0.5)
    if referral_required:
        base *= 0.85
    return base


def score_offer(offer: Offer, service: Optional[Service], now: dt.datetime,
                settings: Optional[Settings] = None) -> float:
    settings = settings or get_settings()
    first = offer.first_seen_at or now
    if first.tzinfo is None:
        first = first.replace(tzinfo=dt.timezone.utc)
    age_hours = max((now - first).total_seconds() / 3600.0, 0.0)

    fresh = freshness_score(age_hours)
    amt = amount_score(offer.amount)
    ease = ease_score(offer.type, offer.referral_required)
    reliab = service.reliability if service else 0.0

    total = (
        settings.score_w_freshness * fresh
        + settings.score_w_amount * amt
        + settings.score_w_ease * ease
        + settings.score_w_reliability * reliab
    )
    return round(total, 4)


def rescore_all(session, settings: Optional[Settings] = None) -> int:
    settings = settings or get_settings()
    now = utcnow()
    offers = session.scalars(select(Offer)).all()
    for offer in offers:
        service = session.get(Service, offer.service_id) if offer.service_id else None
        offer.score = score_offer(offer, service, now, settings)
    log.info("rescored %d offers", len(offers))
    return len(offers)

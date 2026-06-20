"""Persistence + dedup: Service <- Offer <- Signal.

Dedup rules:
  - Service: unique by canonical_domain.
  - Offer: one active offer per (service, offer_type); re-observations update it
    and backfill missing fields rather than creating duplicates.
  - Signal: unique by (source, source_url); skip if already stored.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.signal import Signal as RawSignal
from ..logging_conf import get_logger
from ..models import LeadMetric, Offer, Service, Signal, utcnow
from .classify import Classification

log = get_logger("store")

# Aggregator/social sources used to measure how late the TG ecosystem is.
AGGREGATOR_SOURCES = {"telegram", "telegram_ingest"}


def compute_lead_hours(first_us, first_agg) -> float | None:
    """Hours the aggregators lagged behind us. Positive => we were earlier."""
    if not first_us or not first_agg:
        return None
    a = first_us.replace(tzinfo=None) if first_us.tzinfo else first_us
    b = first_agg.replace(tzinfo=None) if first_agg.tzinfo else first_agg
    return round((b - a).total_seconds() / 3600.0, 2)


def _naive(d):
    if d is None:
        return None
    return d.replace(tzinfo=None) if d.tzinfo else d


def _update_lead_metric(session, offer: Offer, source: str, observed_at) -> None:
    lm = session.scalar(select(LeadMetric).where(LeadMetric.offer_id == offer.id))
    if lm is None:
        lm = LeadMetric(offer_id=offer.id)
        session.add(lm)
        session.flush()
    observed = _naive(observed_at)
    if source in AGGREGATOR_SOURCES:
        cur = _naive(lm.first_seen_in_aggregator)
        if cur is None or observed < cur:
            lm.first_seen_in_aggregator = observed
    else:
        cur = _naive(lm.first_seen_by_us)
        if cur is None or observed < cur:
            lm.first_seen_by_us = observed
    lm.lead_hours = compute_lead_hours(lm.first_seen_by_us, lm.first_seen_in_aggregator)


def _get_or_create_service(session: Session, domain: str, clf: Classification) -> Service:
    svc = session.scalar(select(Service).where(Service.canonical_domain == domain))
    if svc is None:
        svc = Service(
            canonical_domain=domain,
            name=clf.service_name or domain.split(".")[0],
            type=clf.offer_type or "other",
            models=clf.models or None,
        )
        session.add(svc)
        session.flush()
    return svc


def _get_or_create_offer(session: Session, svc: Service, clf: Classification, url: str | None) -> tuple[Offer, bool]:
    offer = session.scalar(
        select(Offer).where(Offer.service_id == svc.id, Offer.type == clf.offer_type)
    )
    created = False
    if offer is None:
        offer = Offer(
            service_id=svc.id,
            type=clf.offer_type,
            amount=clf.amount,
            currency=clf.currency,
            models=clf.models or None,
            claim_steps=clf.claim_steps,
            requirements=clf.requirements,
            referral_required=clf.referral_required,
            url=url,
        )
        session.add(offer)
        session.flush()
        created = True
    else:
        # backfill missing fields from a richer observation
        offer.amount = offer.amount or clf.amount
        offer.currency = offer.currency or clf.currency
        offer.claim_steps = offer.claim_steps or clf.claim_steps
        offer.requirements = offer.requirements or clf.requirements
        offer.url = offer.url or url
        if clf.models and not offer.models:
            offer.models = clf.models
        offer.last_verified_at = utcnow()
    return offer, created


def persist(
    session: Session,
    raw: RawSignal,
    clf: Classification,
    domains: list[str],
    min_confidence: float = 0.4,
) -> dict:
    """Store one classified signal. Returns a small stats dict."""
    stats = {"signals": 0, "offers_created": 0, "offers_updated": 0, "dup": 0}

    # Signal-level dedup by (source, source_url).
    if raw.source_url:
        exists = session.scalar(
            select(Signal.id).where(Signal.source == raw.source, Signal.source_url == raw.source_url)
        )
        if exists:
            stats["dup"] = 1
            return stats

    svc = None
    offer = None
    if clf.is_offer and clf.confidence >= min_confidence and domains:
        svc = _get_or_create_service(session, domains[0], clf)
        offer, created = _get_or_create_offer(session, svc, clf, raw.url)
        stats["offers_created"] = int(created)
        stats["offers_updated"] = int(not created)
        _update_lead_metric(session, offer, raw.source, raw.observed_at)
    elif raw.meta.get("model_release") and raw.url:
        # HF model release: key a pseudo-service per org, one offer per model url.
        org = (raw.meta.get("org") or "hf").lower()
        pseudo = f"hf/{org}"
        svc = session.scalar(select(Service).where(Service.canonical_domain == pseudo))
        if svc is None:
            svc = Service(canonical_domain=pseudo, name=org, type="model_release", status="active")
            session.add(svc)
            session.flush()
        existing = session.scalar(
            select(Offer).where(Offer.service_id == svc.id, Offer.url == raw.url)
        )
        if existing is None:
            offer = Offer(service_id=svc.id, type="model_release", url=raw.url,
                          claim_steps=raw.meta.get("model_id"))
            session.add(offer)
            session.flush()
            stats["model_releases"] = 1
        else:
            offer = existing
    elif raw.meta.get("service_candidate") and domains:
        # Domain-only lead (e.g. certstream): seed a Service for later enrichment,
        # no Offer yet.
        svc = _get_or_create_service(session, domains[0], clf)
        stats["candidates"] = 1

    sig = Signal(
        offer_id=offer.id if offer else None,
        service_id=svc.id if svc else None,
        source=raw.source,
        source_url=raw.source_url,
        url=raw.url,
        raw_text=(raw.raw_text or "")[:8000],
        lang=raw.lang,
        classification=clf.model_dump(),
        confidence=clf.confidence,
        observed_at=raw.observed_at,
    )
    session.add(sig)
    stats["signals"] = 1
    return stats

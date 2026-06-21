"""Persistence + dedup: Service <- Offer <- Signal.

Dedup rules:
  - Service: unique by canonical_domain.
  - Offer: one active offer per (service, offer_type); re-observations update
    it and backfill missing fields rather than creating duplicates.
  - Signal: unique by (source, source_url); skip if already stored.

Uses the platform-agnostic Database protocol — no SQLAlchemy ORM.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from ..core.signal import Signal as RawSignal
from ..db.base import Database, json_decode, json_encode
from ..logging_conf import get_logger
from .classify import Classification
from .normalize import is_blocked_domain, registrable_domain

log = get_logger("store")

# Aggregator/social sources used to measure how late the TG ecosystem is.
AGGREGATOR_SOURCES = {"telegram", "telegram_ingest"}


def compute_lead_hours(first_us, first_agg) -> Optional[float]:
    """Hours the aggregators lagged behind us.  Positive => we were earlier."""
    if not first_us or not first_agg:
        return None
    a = first_us.replace(tzinfo=None) if first_us.tzinfo else first_us
    b = first_agg.replace(tzinfo=None) if first_agg.tzinfo else first_agg
    return round((b - a).total_seconds() / 3600.0, 2)


# ─── Datetime ↔ storage string helpers ───────────────────────────────────────

def _dt_str(d: Optional[dt.datetime]) -> Optional[str]:
    """Datetime → storage string compatible with SQLAlchemy's SQLite format."""
    if d is None:
        return None
    if d.tzinfo is not None:
        d = d.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return d.strftime("%Y-%m-%d %H:%M:%S.%f")


def _dt_parse(s: Optional[str]) -> Optional[dt.datetime]:
    """Storage string → naive UTC datetime."""
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        # Last resort: fromisoformat (handles +00:00 suffix)
        d = dt.datetime.fromisoformat(s)
        return d.replace(tzinfo=None) if d.tzinfo else d
    except ValueError:
        return None


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _get_or_create_service(db: Database, domain: str, clf: Classification) -> int:
    # Consolidate by registrable domain (eTLD+1): app.base44.com -> base44.com.
    reg = registrable_domain(domain) or domain
    rows = db.execute(
        "SELECT id, aliases FROM services WHERE canonical_domain = ?", [reg]
    )
    if rows:
        sid = rows[0]["id"]
        if domain and domain != reg:
            aliases = json_decode(rows[0]["aliases"]) or []
            if domain not in aliases:
                aliases.append(domain)
                db.run("UPDATE services SET aliases=? WHERE id=?",
                       [json_encode(aliases), sid])
        return sid
    aliases = [domain] if domain and domain != reg else []
    db.run(
        "INSERT INTO services (canonical_domain, name, type, models, aliases) "
        "VALUES (?, ?, ?, ?, ?)",
        [reg, reg, clf.offer_type or "other",
         json_encode(clf.models or None), json_encode(aliases or None)],
    )
    return db.execute("SELECT last_insert_rowid() AS id")[0]["id"]


def _get_or_create_offer(
    db: Database,
    service_id: int,
    clf: Classification,
    url: Optional[str],
) -> tuple[int, bool]:
    rows = db.execute(
        "SELECT id, amount, currency, models, claim_steps, requirements, url, effort, unit "
        "FROM offers WHERE service_id = ? AND type = ?",
        [service_id, clf.offer_type],
    )
    if rows:
        row = rows[0]
        offer_id = row["id"]
        # Backfill missing fields from a richer observation.
        new_amount = row["amount"] or clf.amount
        new_currency = row["currency"] or clf.currency
        new_claim_steps = row["claim_steps"] or clf.claim_steps
        new_requirements = row["requirements"] or clf.requirements
        new_url = row["url"] or url
        existing_models = json_decode(row["models"])
        new_models = json_encode(existing_models or clf.models or None)
        if clf.models and not existing_models:
            new_models = json_encode(clf.models)
        db.run(
            "UPDATE offers SET amount=?, currency=?, claim_steps=?, requirements=?, "
            "url=?, models=?, last_verified_at=? WHERE id=?",
            [
                new_amount,
                new_currency,
                new_claim_steps,
                new_requirements,
                new_url,
                new_models,
                _dt_str(dt.datetime.now(dt.timezone.utc)),
                offer_id,
            ],
        )
        # Backfill effort/unit if still NULL
        if clf.effort or clf.unit:
            db.run(
                "UPDATE offers SET effort=?, unit=? WHERE id=? AND (effort IS NULL OR unit IS NULL)",
                [clf.effort, clf.unit, offer_id],
            )
        return offer_id, False
    db.run(
        "INSERT INTO offers (service_id, type, amount, currency, models, "
        "claim_steps, requirements, referral_required, url, effort, unit) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            service_id,
            clf.offer_type,
            clf.amount,
            clf.currency,
            json_encode(clf.models or None),
            clf.claim_steps,
            clf.requirements,
            int(clf.referral_required),
            url,
            clf.effort,
            clf.unit,
        ],
    )
    offer_id = db.execute("SELECT last_insert_rowid() AS id")[0]["id"]
    return offer_id, True


def _update_lead_metric(
    db: Database,
    offer_id: int,
    source: str,
    observed_at: Optional[dt.datetime],
) -> None:
    rows = db.execute(
        "SELECT id, first_seen_by_us, first_seen_in_aggregator "
        "FROM lead_metrics WHERE offer_id = ?",
        [offer_id],
    )
    if rows:
        lm_id = rows[0]["id"]
        first_seen_by_us = _dt_parse(rows[0]["first_seen_by_us"])
        first_seen_in_agg = _dt_parse(rows[0]["first_seen_in_aggregator"])
    else:
        db.run("INSERT INTO lead_metrics (offer_id) VALUES (?)", [offer_id])
        lm_id = db.execute("SELECT last_insert_rowid() AS id")[0]["id"]
        first_seen_by_us = None
        first_seen_in_agg = None

    # Normalize to naive UTC for comparisons.
    observed = (
        observed_at.replace(tzinfo=None) if (observed_at and observed_at.tzinfo) else observed_at
    )

    if source in AGGREGATOR_SOURCES:
        if observed is not None and (first_seen_in_agg is None or observed < first_seen_in_agg):
            first_seen_in_agg = observed
    else:
        if observed is not None and (first_seen_by_us is None or observed < first_seen_by_us):
            first_seen_by_us = observed

    lead_hours = compute_lead_hours(first_seen_by_us, first_seen_in_agg)
    db.run(
        "UPDATE lead_metrics SET first_seen_by_us=?, first_seen_in_aggregator=?, "
        "lead_hours=? WHERE id=?",
        [_dt_str(first_seen_by_us), _dt_str(first_seen_in_agg), lead_hours, lm_id],
    )


# ─── Public API ───────────────────────────────────────────────────────────────

def persist(
    db: Database,
    raw: RawSignal,
    clf: Classification,
    domains: list[str],
    min_confidence: float = 0.4,
) -> dict:
    """Store one classified signal.  Returns a small stats dict."""
    stats: dict[str, int] = {
        "signals": 0,
        "offers_created": 0,
        "offers_updated": 0,
        "dup": 0,
    }

    # Signal-level dedup by (source, source_url).
    if raw.source_url:
        dups = db.execute(
            "SELECT id FROM signals WHERE source = ? AND source_url = ?",
            [raw.source, raw.source_url],
        )
        if dups:
            stats["dup"] = 1
            return stats

    # Anti-noise: platform/aggregator/social/dev-host domains must never become
    # a Service/offer. Drop the signal entirely (logged), EXCEPT HuggingFace
    # model releases, which are keyed by a pseudo hf/<org> service below.
    if domains and is_blocked_domain(domains[0]) and not raw.meta.get("model_release"):
        log.debug("dropping blocked-domain signal: %s (source=%s)", domains[0], raw.source)
        stats["blocked"] = 1
        return stats

    service_id: Optional[int] = None
    offer_id: Optional[int] = None

    if clf.is_offer and clf.confidence >= min_confidence and domains:
        service_id = _get_or_create_service(db, domains[0], clf)
        offer_id, created = _get_or_create_offer(db, service_id, clf, raw.url)
        stats["offers_created"] = int(created)
        stats["offers_updated"] = int(not created)
        _update_lead_metric(db, offer_id, raw.source, raw.observed_at)

    elif raw.meta.get("model_release") and raw.url:
        # HF model release: key a pseudo-service per org, one offer per model URL.
        org = (raw.meta.get("org") or "hf").lower()
        pseudo = f"hf/{org}"
        svc_rows = db.execute(
            "SELECT id FROM services WHERE canonical_domain = ?", [pseudo]
        )
        if svc_rows:
            service_id = svc_rows[0]["id"]
        else:
            db.run(
                "INSERT INTO services (canonical_domain, name, type, status) "
                "VALUES (?, ?, 'model_release', 'active')",
                [pseudo, org],
            )
            service_id = db.execute("SELECT last_insert_rowid() AS id")[0]["id"]

        existing = db.execute(
            "SELECT id FROM offers WHERE service_id = ? AND url = ?",
            [service_id, raw.url],
        )
        if not existing:
            db.run(
                "INSERT INTO offers (service_id, type, url, claim_steps) "
                "VALUES (?, 'model_release', ?, ?)",
                [service_id, raw.url, raw.meta.get("model_id")],
            )
            offer_id = db.execute("SELECT last_insert_rowid() AS id")[0]["id"]
            stats["model_releases"] = 1
        else:
            offer_id = existing[0]["id"]

    elif raw.meta.get("service_candidate") and domains:
        # Domain-only lead (e.g. certstream): seed a Service for later enrichment.
        service_id = _get_or_create_service(db, domains[0], clf)
        stats["candidates"] = 1

    db.run(
        "INSERT INTO signals "
        "(offer_id, service_id, source, source_url, url, raw_text, lang, "
        "classification, confidence, observed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            offer_id,
            service_id,
            raw.source,
            raw.source_url,
            raw.url,
            (raw.raw_text or "")[:8000],
            raw.lang,
            json_encode(clf.model_dump()),
            clf.confidence,
            _dt_str(raw.observed_at),
        ],
    )
    stats["signals"] = 1
    return stats

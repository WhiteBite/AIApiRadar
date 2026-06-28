"""Main probe() entry, ProbeResult, crt.sh age lookup and the enrich_service
orchestration (DB-protocol + legacy ORM paths).

Network functions take an httpx.AsyncClient so tests can inject a MockTransport.

enrich_service() accepts either:
  - (Database, service_id: int, client)   — new protocol path (watchdog)
  - (Session, Service, client)             — backward compat for legacy tests
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

import httpx

from ..logging_conf import get_logger
from ..models import utcnow
from ..util.dtutil import to_storage_str as _dt_str, parse_naive as _dt_parse_local
from .detect import detect_amount, detect_engine, detect_models
from .offer_paths import (
    MAX_PROBE_REQUESTS,
    PRICING_TRIGGERS,
    _RELAY_RESERVE,
    _ReqBudget,
    _probe_relay_endpoints,
)
from .sitemap import _discover_offer_urls
from .text import _make_description, _title, _visible_text

log = get_logger("enrich")


@dataclass(slots=True)
class ProbeResult:
    alive: bool = False
    status: Optional[int] = None
    title: Optional[str] = None
    engine: Optional[str] = None
    has_pricing: bool = False
    pricing_triggers: bool = False
    description: Optional[str] = None      # short blurb for the UI
    models: list[str] = field(default_factory=list)  # models detected on page
    amount: Optional[float] = None         # credit/$ amount detected on page
    is_relay: bool = False                 # answered a relay-engine endpoint
    notice: Optional[str] = None           # text from /api/notice (offer copy)


def earliest_not_before(data: list[dict]) -> Optional[dt.datetime]:
    """Parse crt.sh JSON rows -> earliest not_before as tz-aware UTC datetime."""
    best: Optional[dt.datetime] = None
    for row in data or []:
        raw = row.get("not_before")
        if not raw:
            continue
        try:
            d = dt.datetime.fromisoformat(raw)
        except ValueError:
            continue
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        if best is None or d < best:
            best = d
    return best


def reliability_score(alive: bool, has_pricing: bool, engine_known: bool,
                      age_days: Optional[float]) -> float:
    s = 0.0
    if alive:
        s += 0.5
    if has_pricing:
        s += 0.2
    if engine_known:
        s += 0.1
    if age_days is not None:
        s += min(age_days / 30.0, 1.0) * 0.2  # older domain == more trust
    return round(min(s, 1.0), 3)


async def probe(domain: str, client: httpx.AsyncClient) -> ProbeResult:
    res = ProbeResult()
    blob = ""
    # Reserve a few slots for the relay-endpoint probe; the root fetch + the
    # offer-path sweep + the sitemap crawl share the rest so a single probe
    # stays within MAX_PROBE_REQUESTS total GETs.
    budget = _ReqBudget(MAX_PROBE_REQUESTS - _RELAY_RESERVE)

    if budget.take():
        try:
            r = await client.get(f"https://{domain}/")
            res.status = r.status_code
            res.alive = r.status_code < 500
            text = r.text if r.status_code < 400 else ""
            res.title = _title(text)
            res.engine = detect_engine(text, dict(r.headers))
            res.description = _make_description(text)
            blob += " " + _visible_text(text)
        except Exception:
            log.debug("probe root failed for %s", domain, exc_info=False)

    async def _scan_offer_path(path: str) -> bool:
        """Fetch one offer path; fold any 200 content into the result/blob.

        Returns True when the page returned 200 with real content (so the caller
        can decide whether fallbacks are still needed). Mirrors the original
        /pricing handling: a 200 sets has_pricing, trigger words set
        pricing_triggers, and the visible text feeds model/amount detection.
        """
        nonlocal blob
        if not budget.take():
            return False
        try:
            r = await client.get(f"https://{domain}{path}")
        except Exception:
            return False
        if r.status_code != 200:
            return False
        text = r.text or ""
        res.has_pricing = True
        low = text.lower()
        if any(t in low for t in PRICING_TRIGGERS):
            res.pricing_triggers = True
        if text.strip():
            blob += " " + _visible_text(text)
            if not res.description:
                res.description = _make_description(text)
            return True
        return False

    # Bounded offer-path sweep. Always try the two most common pages; only fall
    # back to the rarer ones if neither yielded real content. Stop the moment a
    # trigger word is found, and never exceed the shared request budget.
    got_primary = False
    for path in ("/pricing", "/plans"):
        if await _scan_offer_path(path):
            got_primary = True
        if res.pricing_triggers:
            break
    if not res.pricing_triggers and not got_primary:
        for path in ("/billing", "/subscribe", "/redeem"):
            await _scan_offer_path(path)
            if res.pricing_triggers:
                break

    # Relay-endpoint probe: skip only when the offer-path sweep already gave a
    # rich offer (pricing triggers AND a known relay engine). Otherwise try the
    # endpoints — this is where silent relays and empty-/pricing sites reveal
    # themselves. Keeps requests off clearly-commercial sites with full pricing.
    if not (res.has_pricing and res.pricing_triggers and res.engine):
        blob += await _probe_relay_endpoints(domain, client, res)

    # Last resort: if nothing so far surfaced a trigger, mine robots.txt and the
    # sitemap for offer URLs at non-standard paths and scan up to 3 of them.
    # Guarded + budget-bounded so it can never explode the request count.
    if not res.pricing_triggers and budget.remaining > 0:
        try:
            offer_urls = await _discover_offer_urls(domain, client, budget)
        except Exception:
            offer_urls = []
        for url in offer_urls[:3]:
            if not budget.take():
                break
            try:
                r = await client.get(url)
            except Exception:
                continue
            if r.status_code != 200:
                continue
            text = r.text or ""
            res.has_pricing = True
            low = text.lower()
            if any(t in low for t in PRICING_TRIGGERS):
                res.pricing_triggers = True
            if text.strip():
                blob += " " + _visible_text(text)
                if not res.description:
                    res.description = _make_description(text)
            if res.pricing_triggers:
                break

    # Facts parsed off the page text (title + body + offer pages + relay endpoints).
    fact_blob = f"{res.title or ''} {res.description or ''} {res.notice or ''} {blob}"
    res.models = detect_models(fact_blob) or res.models
    res.amount = detect_amount(fact_blob)
    return res


async def crtsh_earliest(domain: str, client: httpx.AsyncClient) -> Optional[dt.datetime]:
    try:
        r = await client.get(f"https://crt.sh/?q={domain}&output=json")
        if r.status_code == 200:
            return earliest_not_before(r.json())
    except Exception:
        log.debug("crt.sh failed for %s", domain, exc_info=False)
    return None


# ─── Storage helpers (private) ────────────────────────────────────────────────

# ─── New Database-protocol path ───────────────────────────────────────────────

async def _enrich_service_db(db, service_id: int, client: httpx.AsyncClient,
                             do_crtsh: bool = True) -> None:
    from ..db.base import Database

    rows = db.execute(
        "SELECT canonical_domain, domain_first_seen FROM services WHERE id = ?",
        [service_id],
    )
    if not rows:
        log.warning("enrich_service: service %d not found", service_id)
        return

    domain = rows[0]["canonical_domain"]
    existing_age = _dt_parse_local(rows[0]["domain_first_seen"])
    p = await probe(domain, client)
    now = utcnow()

    # crt.sh is slow; only hit it when the domain age is still unknown (it never
    # changes once known) and not explicitly disabled. Reuse the stored age for
    # the reliability calc so skipping crt.sh doesn't regress the score.
    age = existing_age
    if do_crtsh and existing_age is None:
        fetched = await crtsh_earliest(domain, client)
        if fetched:
            age = fetched

    status = "active" if p.alive else "dead"
    engine = p.engine
    age_days = (
        (now.replace(tzinfo=None) - age.replace(tzinfo=None)).total_seconds() / 86400.0
        if age else None
    )
    rel = reliability_score(p.alive, p.has_pricing, bool(p.engine), age_days)
    # Preserve a previously-known age if we didn't (re)fetch one.
    domain_first_seen = _dt_str(age) if age else rows[0]["domain_first_seen"]

    db.run(
        "UPDATE services "
        "SET status=?, engine=?, reliability=?, domain_first_seen=?, last_checked=? "
        "WHERE id=?",
        [status, engine, rel, domain_first_seen, _dt_str(now), service_id],
    )

    # Backfill the service's offers with facts parsed off the page. Use the page
    # title as a description fallback so the field becomes non-NULL even when a
    # site has no meta description (otherwise it'd be re-enriched forever).
    desc = p.description or p.title
    if desc or p.models or p.amount is not None:
        import json as _json
        offers = db.execute(
            "SELECT id, amount, models, description FROM offers WHERE service_id=?",
            [service_id],
        )
        for off in offers:
            sets, args = [], []
            if desc:
                sets.append("description=?")
                args.append(desc)
            if p.models and not off["models"]:
                sets.append("models=?")
                args.append(_json.dumps(p.models))
            if p.amount is not None and not off["amount"]:
                sets.append("amount=?")
                args.append(p.amount)
            if sets:
                args.append(off["id"])
                db.run(f"UPDATE offers SET {', '.join(sets)} WHERE id=?", args)

    log.info(
        "enriched %s status=%s engine=%s reliability=%.2f models=%s amount=%s",
        domain, status, engine, rel, p.models, p.amount,
    )


# ─── Legacy SQLAlchemy-session path (backward compat) ────────────────────────

async def _enrich_service_orm(session, service, client: httpx.AsyncClient) -> None:
    p = await probe(service.canonical_domain, client)
    age = await crtsh_earliest(service.canonical_domain, client)
    now = utcnow()

    service.status = "active" if p.alive else "dead"
    if p.engine:
        service.engine = p.engine
    if age:
        service.domain_first_seen = age
    age_days = (now - age).total_seconds() / 86400.0 if age else None
    service.reliability = reliability_score(p.alive, p.has_pricing, bool(p.engine), age_days)
    service.last_checked = now
    log.info(
        "enriched %s status=%s engine=%s reliability=%.2f",
        service.canonical_domain, service.status, service.engine, service.reliability,
    )


# ─── Public entry point ───────────────────────────────────────────────────────

async def enrich_service(db_or_session, service_or_id, client: httpx.AsyncClient,
                         do_crtsh: bool = True) -> None:
    """Probe a service and update its fields.

    New usage:   enrich_service(db, service_id, client, do_crtsh=...)
    Legacy usage: enrich_service(session, service_orm_obj, client)
    """
    from ..db.base import Database

    if isinstance(db_or_session, Database):
        await _enrich_service_db(db_or_session, service_or_id, client, do_crtsh=do_crtsh)
    else:
        await _enrich_service_orm(db_or_session, service_or_id, client)

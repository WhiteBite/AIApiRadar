"""Enrichment / resolution for Service rows.

Probes a service to answer: is it alive? does it have a /pricing page with
offer triggers? what relay engine powers it? how old is the domain (crt.sh)?
These feed the reliability score used by the scorer and watchdog.

Network functions take an httpx.AsyncClient so tests can inject a MockTransport.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx

from .logging_conf import get_logger
from .models import Service, utcnow

log = get_logger("enrich")

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

# Open-source relay engines these services are typically built on.
# Strict markers only (hyphenated names / repo authors / admin-panel titles) to
# avoid false positives like "...in one API call..." on unrelated sites.
ENGINE_BODY_MARKS = {
    "new-api": ("new-api", "newapi", "calcium-ion"),
    "one-api": ("one-api", "songquanpeng"),
    "sub2api": ("sub2api", "sub-2-api"),
    "cliproxyapi": ("cliproxyapi", "cli-proxy-api"),
}
# Admin panels of these engines set an exact <title>.
ENGINE_TITLE_EXACT = {
    "new api": "new-api",
    "one api": "one-api",
    "sub2api": "sub2api",
}

PRICING_TRIGGERS = (
    "free credit", "free trial", "no credit card", "no card", "$",
    "注册送", "免费", "trial", "credits", "送额度",
)


@dataclass(slots=True)
class ProbeResult:
    alive: bool = False
    status: Optional[int] = None
    title: Optional[str] = None
    engine: Optional[str] = None
    has_pricing: bool = False
    pricing_triggers: bool = False


def detect_engine(text: str, headers: Optional[dict] = None) -> Optional[str]:
    # Exact admin-panel title is the most reliable signal.
    title = _title(text)
    if title and title.strip().lower() in ENGINE_TITLE_EXACT:
        return ENGINE_TITLE_EXACT[title.strip().lower()]
    blob = (text or "").lower()
    if headers:
        blob += " " + " ".join(f"{k}:{v}" for k, v in headers.items()).lower()
    for engine, marks in ENGINE_BODY_MARKS.items():
        if any(m in blob for m in marks):
            return engine
    return None


def _title(html: str) -> Optional[str]:
    m = _TITLE_RE.search(html or "")
    return m.group(1).strip()[:200] if m else None


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
    try:
        r = await client.get(f"https://{domain}/")
        res.status = r.status_code
        res.alive = r.status_code < 500
        text = r.text if r.status_code < 400 else ""
        res.title = _title(text)
        res.engine = detect_engine(text, dict(r.headers))
    except Exception:
        log.debug("probe root failed for %s", domain, exc_info=False)
    try:
        r = await client.get(f"https://{domain}/pricing")
        if r.status_code == 200:
            res.has_pricing = True
            low = r.text.lower()
            res.pricing_triggers = any(t in low for t in PRICING_TRIGGERS)
    except Exception:
        pass
    return res


async def crtsh_earliest(domain: str, client: httpx.AsyncClient) -> Optional[dt.datetime]:
    try:
        r = await client.get(f"https://crt.sh/?q={domain}&output=json")
        if r.status_code == 200:
            return earliest_not_before(r.json())
    except Exception:
        log.debug("crt.sh failed for %s", domain, exc_info=False)
    return None


async def enrich_service(session, service: Service, client: httpx.AsyncClient) -> None:
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
    log.info("enriched %s status=%s engine=%s reliability=%.2f",
             service.canonical_domain, service.status, service.engine, service.reliability)

"""Enrichment / resolution for Service rows.

Probes a service to answer: is it alive? does it have a /pricing page with
offer triggers? what relay engine powers it? how old is the domain (crt.sh)?
These feed the reliability score used by the scorer and watchdog.

Network functions take an httpx.AsyncClient so tests can inject a MockTransport.

enrich_service() accepts either:
  - (Database, service_id: int, client)   — new protocol path (watchdog)
  - (Session, Service, client)             — backward compat for legacy tests
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx

from .logging_conf import get_logger
from .models import utcnow

log = get_logger("enrich")

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_DESC_RE = re.compile(
    r'<meta[^>]+(?:name|property)\s*=\s*["\'](?:description|og:description)["\'][^>]*'
    r'content\s*=\s*["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
_META_DESC_RE2 = re.compile(
    r'<meta[^>]+content\s*=\s*["\'](.*?)["\'][^>]*'
    r'(?:name|property)\s*=\s*["\'](?:description|og:description)["\']',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_WS_RE = re.compile(r"\s+")

# Model keywords → canonical label (for facts parsed off the service page).
#
# Split into two groups to avoid false positives:
#
#   _SUBSTR_TOKENS  — longer, distinctive strings safe for plain substring
#                     matching (e.g. "claude", "gemini", "deepseek").
#
#   _EXACT_TOKENS   — short / ambiguous tokens that must NOT match inside
#                     unrelated words.  For these we require that the token
#                     is NOT immediately preceded or followed by a letter,
#                     e.g.  "gpt"  matches "gpt-4" and "use gpt today" but
#                     NOT "egypt" or "agpt".  A pre-compiled regex is built
#                     for each token in _EXACT_TOKENS below.
_SUBSTR_TOKENS: dict[str, str] = {
    "claude": "claude", "opus": "opus", "sonnet": "sonnet", "haiku": "haiku",
    "gpt-5": "gpt", "gpt-4": "gpt", "gpt4": "gpt", "openai": "gpt",
    "gemini": "gemini", "deepseek": "deepseek",
    "grok": "grok", "llama": "llama", "qwen": "qwen",
    "mistral": "mistral", "kimi": "kimi",
}

# Short tokens that require a non-letter boundary on both sides.
_EXACT_TOKENS: dict[str, str] = {
    "gpt": "gpt",   # would match "egypt", "agpt" etc. without boundary check
    "o1":  "gpt",   # very short; matches "o1" in scientific/version strings
    "o3":  "gpt",   # same
    "glm": "glm",   # would match inside longer words
}

# Pre-compile one regex per exact token: (?<![a-z])TOKEN(?![a-z])
# Applied to the already-lowercased text blob.
_EXACT_RES: dict[str, tuple[re.Pattern, str]] = {
    token: (re.compile(r"(?<![a-z])" + re.escape(token) + r"(?![a-z])"), label)
    for token, label in _EXACT_TOKENS.items()
}
_AMOUNT_USD_RE = re.compile(r"\$\s?(\d{1,3}(?:[,\s]?\d{3})*(?:\.\d+)?)")
_AMOUNT_CREDIT_RE = re.compile(r"(\d{2,6})\s*(?:credits?|刀|额度|points?|баллов)", re.IGNORECASE)

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

# Standard endpoints exposed by relay engines (new-api / one-api / sub2api).
# These reveal an offer even when /pricing is empty or missing — closing the
# "offer only on homepage / no pricing page" blind spot. All are anonymous GETs.
RELAY_STATUS_PATH = "/api/status"   # JSON {data:{version,...}} — relay fingerprint
RELAY_MODELS_PATH = "/v1/models"    # OpenAI-format model list — offer signal
RELAY_NOTICE_PATH = "/api/notice"   # operator notice, often "注册即送 $X"

# Candidate pages that may carry an offer when /pricing is empty / a JS SPA.
# probe() never fetches all 13 — it tries a bounded subset (see probe()).
OFFER_PATHS = ("/pricing", "/plans", "/billing", "/subscribe", "/upgrade",
               "/redeem", "/promo", "/coupon", "/referral", "/help", "/faq",
               "/docs", "/developers")

# Hard ceiling on the number of HTTP GETs a single probe() may make. Bounds the
# cost of the offer-path sweep + robots/sitemap crawl so one domain can never
# explode into dozens of requests. Root + offer-paths + sitemap share most of
# it; a small reserve is kept for the 3 relay-endpoint probes.
MAX_PROBE_REQUESTS = 10
_RELAY_RESERVE = 3  # requests held back for _probe_relay_endpoints()

# Path keywords that mark a URL (from robots.txt / sitemap.xml) as offer-bearing.
_OFFER_URL_RE = re.compile(
    r"pricing|plans|billing|subscribe|redeem|promo|coupon|trial|credits|free",
    re.IGNORECASE,
)
_SITEMAP_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)


class _ReqBudget:
    """Tiny shared counter so a probe never exceeds MAX_PROBE_REQUESTS GETs."""

    __slots__ = ("remaining",)

    def __init__(self, n: int) -> None:
        self.remaining = n

    def take(self) -> bool:
        """Consume one request slot. Returns False when the budget is spent."""
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True


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


def _meta_description(html: str) -> Optional[str]:
    for rx in (_META_DESC_RE, _META_DESC_RE2):
        m = rx.search(html or "")
        if m:
            txt = _clean_text(m.group(1))
            if len(txt) > 20:
                return txt[:300]
    return None


def _clean_text(s: str) -> str:
    import html as _html
    return _WS_RE.sub(" ", _html.unescape(s or "")).strip()


def _visible_text(html: str, cap: int = 4000) -> str:
    no_scripts = _SCRIPT_STYLE_RE.sub(" ", html or "")
    return _clean_text(_TAG_RE.sub(" ", no_scripts))[:cap]


def _make_description(html: str) -> Optional[str]:
    """Prefer meta/og description; fall back to the first real paragraph."""
    meta = _meta_description(html)
    if meta:
        return meta
    text = _visible_text(html, cap=400)
    return text[:280] if len(text) > 40 else None


def detect_models(text: str) -> list[str]:
    """Return canonical model labels found in *text*.

    Uses two matching strategies:
    - Substring match for long, distinctive tokens (claude, gemini, deepseek …)
    - Word-boundary regex for short/ambiguous tokens (gpt, o1, o3, glm) to
      avoid false positives like "egypt" → gpt or "o1" inside a version string.
    """
    blob = (text or "").lower()
    out: list[str] = []
    # Substring pass — long tokens, safe without boundaries.
    for kw, label in _SUBSTR_TOKENS.items():
        if kw in blob and label not in out:
            out.append(label)
    # Boundary pass — short tokens, require non-letter on both sides.
    for _token, (rx, label) in _EXACT_RES.items():
        if label not in out and rx.search(blob):
            out.append(label)
    return out


def detect_amount(text: str) -> Optional[float]:
    """Largest plausible FREE-credit amount, only when a trigger word sits next
    to the number (avoids grabbing random page figures like revenue/$80,170)."""
    t = text or ""
    low = t.lower()
    triggers = (
        "free", "credit", "trial", "bonus", "gift", "voucher", "sign up", "signup",
        "get $", "claim", "注册送", "免费", "送", "额度", "赠", "бесплатн", "кредит", "триал",
    )
    best: Optional[float] = None
    for rx in (_AMOUNT_USD_RE, _AMOUNT_CREDIT_RE):
        for m in rx.finditer(t):
            try:
                val = float(m.group(1).replace(",", "").replace(" ", ""))
            except ValueError:
                continue
            if not (1 <= val <= 5000):  # free credits are rarely above this
                continue
            window = low[max(0, m.start() - 40):m.end() + 40]
            if any(k in window for k in triggers):
                if best is None or val > best:
                    best = val
    return best


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


async def _probe_relay_endpoints(domain: str, client: httpx.AsyncClient,
                                 res: ProbeResult) -> str:
    """Probe standard relay-engine endpoints. Returns extra text for fact parsing.

    Relay panels (new-api/one-api/sub2api) expose an offer even when /pricing is
    empty: /v1/models lists the models on tap, /api/notice carries the operator's
    "注册送 $X" copy, /api/status confirms it's a relay. All anonymous GETs.
    """
    extra = ""

    # /api/status — relay fingerprint (JSON with a version field).
    try:
        r = await client.get(f"https://{domain}{RELAY_STATUS_PATH}")
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and "json" in ctype:
            data = r.json()
            if isinstance(data, dict) and ("data" in data or "version" in data):
                res.is_relay = True
    except Exception:
        pass

    # /v1/models — OpenAI-format model list. Presence == it's an LLM API.
    try:
        r = await client.get(f"https://{domain}{RELAY_MODELS_PATH}")
        if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
            data = r.json()
            items = data.get("data") if isinstance(data, dict) else None
            ids = [m.get("id", "") for m in items if isinstance(m, dict)] if items else []
            if ids:
                res.is_relay = True
                extra += " " + " ".join(ids)[:2000]
                for m in detect_models(" ".join(ids)):
                    if m not in res.models:
                        res.models.append(m)
    except Exception:
        pass

    # /api/notice — operator notice, often the actual free-credit promo text.
    try:
        r = await client.get(f"https://{domain}{RELAY_NOTICE_PATH}")
        if r.status_code == 200:
            txt = _visible_text(r.text, cap=2000)
            if txt:
                low = txt.lower()
                if any(t in low for t in PRICING_TRIGGERS):
                    res.pricing_triggers = True
                    res.notice = txt[:300]
                extra += " " + txt
    except Exception:
        pass

    if res.is_relay and not res.engine:
        res.engine = "relay"  # generic: confirmed relay, specific engine unknown
    return extra


async def _discover_offer_urls(domain: str, client: httpx.AsyncClient,
                               budget: "_ReqBudget | None" = None) -> list[str]:
    """Crawl robots.txt + sitemap.xml to find offer-bearing URLs.

    Used as a last resort when the fixed OFFER_PATHS sweep found no pricing
    triggers — e.g. a site whose offer lives at a non-standard path that's only
    discoverable via its sitemap. Returns absolute URLs whose path matches an
    offer keyword (pricing/plans/billing/redeem/trial/credits/free/…), capped at
    5. Fully guarded: any failure (missing robots, 404 sitemap, bad XML) yields
    an empty/short list and never raises.
    """
    def _take() -> bool:
        return budget.take() if budget is not None else True

    sitemaps: list[str] = []

    # robots.txt → collect any "Sitemap:" directives.
    if _take():
        try:
            r = await client.get(f"https://{domain}/robots.txt")
            if r.status_code == 200:
                for line in (r.text or "").splitlines():
                    line = line.strip()
                    if line.lower().startswith("sitemap:"):
                        sm = line.split(":", 1)[1].strip()
                        if sm:
                            sitemaps.append(sm)
        except Exception:
            pass

    # Always also try the conventional sitemap location.
    sitemaps.append(f"https://{domain}/sitemap.xml")

    locs: list[str] = []
    seen: set[str] = set()
    for sm in sitemaps:
        if sm in seen:
            continue
        seen.add(sm)
        if not _take():
            break
        try:
            r = await client.get(sm)
            if r.status_code == 200:
                for m in _SITEMAP_LOC_RE.finditer(r.text or ""):
                    loc = m.group(1).strip()
                    if loc:
                        locs.append(loc)
        except Exception:
            continue

    out: list[str] = []
    for loc in locs:
        try:
            path = httpx.URL(loc).path or ""
        except Exception:
            path = loc
        if _OFFER_URL_RE.search(path) and loc not in out:
            out.append(loc)
            if len(out) >= 5:
                break
    return out


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

def _dt_str(d: Optional[dt.datetime]) -> Optional[str]:
    """Datetime → storage string (naive UTC, SQLAlchemy-compatible format)."""
    if d is None:
        return None
    if d.tzinfo is not None:
        d = d.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return d.strftime("%Y-%m-%d %H:%M:%S.%f")


def _dt_parse_local(s: Optional[str]) -> Optional[dt.datetime]:
    """Storage string → naive UTC datetime (mirror of store._dt_parse)."""
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        d = dt.datetime.fromisoformat(s)
        return d.replace(tzinfo=None) if d.tzinfo else d
    except ValueError:
        return None


# ─── New Database-protocol path ───────────────────────────────────────────────

async def _enrich_service_db(db, service_id: int, client: httpx.AsyncClient,
                             do_crtsh: bool = True) -> None:
    from .db.base import Database

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
    from .db.base import Database

    if isinstance(db_or_session, Database):
        await _enrich_service_db(db_or_session, service_or_id, client, do_crtsh=do_crtsh)
    else:
        await _enrich_service_orm(db_or_session, service_or_id, client)

"""Offer-path constants, the per-probe request budget and the relay-endpoint
sweep.

Relay engines (new-api / one-api / sub2api) expose anonymous endpoints that
reveal an offer even when /pricing is empty. The constants here also drive the
bounded offer-path sweep in ``probe()``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from .detect import detect_models
from .text import _visible_text

if TYPE_CHECKING:
    from .probe import ProbeResult

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


async def _probe_relay_endpoints(domain: str, client: httpx.AsyncClient,
                                 res: "ProbeResult") -> str:
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

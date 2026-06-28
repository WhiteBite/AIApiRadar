"""Phase 3 tests: enrich (probe/crt.sh/engine/reliability), scorer, watchdog.
Network paths use httpx.MockTransport (no real requests)."""
from __future__ import annotations

import asyncio
import datetime as dt

import httpx

from aiapiradar.enrich import (
    detect_engine, earliest_not_before, reliability_score, probe,
    crtsh_earliest, enrich_service,
)
from aiapiradar.scorer import (
    freshness_score, amount_score, ease_score, score_offer, rescore_all,
)


# --- pure enrich helpers ---------------------------------------------------
def test_detect_engine():
    assert detect_engine("<title>New API</title>") == "new-api"
    assert detect_engine("Powered by Sub2API footer") == "sub2api"
    assert detect_engine("<title>One API</title>") == "one-api"
    assert detect_engine("just a landing page") is None
    # must NOT false-positive on prose mentioning 'one API'
    assert detect_engine("<title>Nanonets</title> do it all in one API call") is None


def test_earliest_not_before():
    data = [
        {"not_before": "2026-05-13T16:12:20"},
        {"not_before": "2026-04-30T14:41:56"},
        {"not_before": "bad-date"},
    ]
    d = earliest_not_before(data)
    assert d is not None and (d.month, d.day) == (4, 30)
    assert d.tzinfo is not None


def test_reliability_monotonic():
    assert reliability_score(False, False, False, None) == 0.0
    assert reliability_score(True, True, True, 30) == 1.0
    assert reliability_score(True, True, True, 30) > reliability_score(True, False, False, None)


# --- scorer pure -----------------------------------------------------------
def test_scorer_pure():
    assert freshness_score(0) == 1.0
    assert abs(freshness_score(24) - 0.5) < 1e-9
    assert amount_score(400) == 1.0
    assert amount_score(100) == 0.5
    assert amount_score(None) == 0.0
    assert ease_score("saas_trial", False) > ease_score("grant", False)
    assert ease_score("saas_trial", True) < ease_score("saas_trial", False)


# --- enrich network via MockTransport -------------------------------------
def _handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "crt.sh" in url:
        return httpx.Response(200, json=[{"not_before": "2026-04-30T14:41:56"}])
    if url.endswith("/pricing"):
        return httpx.Response(200, text="Start free with $200 in credits, no card")
    return httpx.Response(200, text="<title>New API</title> welcome")


def test_probe_and_crtsh():
    async def run():
        transport = httpx.MockTransport(_handler)
        async with httpx.AsyncClient(transport=transport) as client:
            p = await probe("freemodel.dev", client)
            age = await crtsh_earliest("freemodel.dev", client)
            return p, age
    p, age = asyncio.run(run())
    assert p.alive and p.status == 200
    assert p.engine == "new-api"
    assert p.has_pricing and p.pricing_triggers
    assert age is not None and (age.month, age.day) == (4, 30)


# --- enrich_service + scorer over temp DB ---------------------------------
def test_enrich_service_updates_fields(db_env):
    from aiapiradar.db import get_db
    from tests.factories import make_service

    service_id = make_service("freemodel.dev", name="FreeModel", type="relay")

    async def run():
        transport = httpx.MockTransport(_handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with get_db() as db:
                await enrich_service(db, service_id, client)

    asyncio.run(run())
    with get_db() as db:
        svc = db.execute(
            "SELECT status, engine, domain_first_seen, reliability "
            "FROM services WHERE canonical_domain = ?",
            ["freemodel.dev"],
        )[0]
    assert svc["status"] == "active"
    assert svc["engine"] == "new-api"
    assert svc["domain_first_seen"] is not None
    assert svc["reliability"] > 0.8


def test_rescore_orders_offers(db_env):
    import datetime as dt

    from aiapiradar.db import get_db
    from aiapiradar.models import utcnow
    from tests.factories import make_offer, make_service

    svc_id = make_service("x.ai", type="other", reliability=0.5)
    now = utcnow()
    make_offer(svc_id, type="saas_trial", amount=200, first_seen_at=now)
    make_offer(svc_id, type="grant", amount=10,
               first_seen_at=now - dt.timedelta(hours=72), referral_required=True)

    with get_db() as db:
        n = rescore_all(db)
        assert n == 2
        offers = {r["type"]: r["score"]
                  for r in db.execute("SELECT type, score FROM offers")}
    assert offers["saas_trial"] > offers["grant"]
    assert all(0.0 <= v <= 1.0 for v in offers.values())

"""Phase 5 tests: notifier (Telegram via MockTransport) + lead metrics."""
from __future__ import annotations

import asyncio
import datetime as dt

import httpx

from aiapiradar.pipeline.store import compute_lead_hours


def _reset_db(tmp_path, monkeypatch, name="p5.db"):
    monkeypatch.setenv("AIRADAR_DB_URL", f"sqlite:///{tmp_path / name}")
    import aiapiradar.config as config
    import aiapiradar.db as db
    config.get_settings.cache_clear()
    db._engine = None
    db._SessionFactory = None
    db.init_db()
    return db


# --- lead metrics ----------------------------------------------------------
def test_compute_lead_hours():
    us = dt.datetime(2026, 4, 30, 12, 0, 0)
    agg = dt.datetime(2026, 5, 13, 12, 0, 0)
    assert compute_lead_hours(us, agg) == 13 * 24.0
    assert compute_lead_hours(us, None) is None
    assert compute_lead_hours(None, agg) is None


def test_lead_metric_recorded_via_pipeline(tmp_path, monkeypatch):
    db = _reset_db(tmp_path, monkeypatch)
    from aiapiradar.pipeline.pipeline import Pipeline
    from aiapiradar.pipeline.classify import HeuristicClassifier
    from aiapiradar.core.signal import Signal
    from aiapiradar.models import LeadMetric, Offer

    pipe = Pipeline(classifier=HeuristicClassifier())
    t0 = dt.datetime(2026, 4, 30, 12, 0, 0, tzinfo=dt.timezone.utc)
    t1 = dt.datetime(2026, 5, 13, 12, 0, 0, tzinfo=dt.timezone.utc)
    # we discover it first (forum), aggregator (telegram) sees it later
    ours = Signal(source="nodeseek", raw_text="freemodel.dev $300 free credits register",
                  url="https://freemodel.dev", source_url="https://nodeseek.com/p/1", observed_at=t0)
    agg = Signal(source="telegram", raw_text="freemodel.dev $300 free credits register",
                 url="https://freemodel.dev", source_url="https://t.me/c/1", observed_at=t1)
    pipe.process_signals([ours, agg])

    with db.session_scope() as s:
        offer = s.query(Offer).one()
        lm = s.query(LeadMetric).filter_by(offer_id=offer.id).one()
        assert lm.first_seen_by_us is not None
        assert lm.first_seen_in_aggregator is not None
        assert lm.lead_hours == 13 * 24.0  # we were 13 days earlier


# --- notifier --------------------------------------------------------------
def test_notifier_sends_once(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRADAR_TG_BOT_TOKEN", "test-token")
    monkeypatch.setenv("AIRADAR_TG_CHAT_ID", "123")
    monkeypatch.setenv("AIRADAR_NOTIFY_MIN_SCORE", "0.6")
    db = _reset_db(tmp_path, monkeypatch, name="p5n.db")

    from aiapiradar.models import Service, Offer, utcnow
    with db.session_scope() as s:
        svc = Service(canonical_domain="freemodel.dev", name="FreeModel", type="relay", status="active")
        s.add(svc)
        s.flush()
        s.add(Offer(service_id=svc.id, type="relay", amount=300, currency="USD",
                    models=["gpt"], score=0.9, first_seen_at=utcnow()))   # above threshold
        s.add(Offer(service_id=svc.id, type="saas_trial", amount=5, score=0.2,
                    first_seen_at=utcnow()))                              # below threshold

    sent_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert "sendMessage" in str(request.url)
        sent_payloads.append(request.content)
        return httpx.Response(200, json={"ok": True})

    from aiapiradar.notifier import notify_new_offers

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await notify_new_offers(client=client)

    n1 = asyncio.run(run())
    assert n1 == 1                       # only the score>=0.6 offer
    assert len(sent_payloads) == 1

    # second run: already notified -> nothing sent
    n2 = asyncio.run(run())
    assert n2 == 0


def test_notifier_disabled_without_token(tmp_path, monkeypatch):
    monkeypatch.delenv("AIRADAR_TG_BOT_TOKEN", raising=False)
    monkeypatch.delenv("AIRADAR_TG_CHAT_ID", raising=False)
    _reset_db(tmp_path, monkeypatch, name="p5d.db")
    from aiapiradar.notifier import notify_new_offers
    assert asyncio.run(notify_new_offers()) == 0

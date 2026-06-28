"""Phase 5 tests: notifier (Telegram via MockTransport) + lead metrics."""
from __future__ import annotations

import asyncio
import datetime as dt

import httpx

from aiapiradar.pipeline.store import compute_lead_hours


# --- lead metrics ----------------------------------------------------------
def test_compute_lead_hours():
    us = dt.datetime(2026, 4, 30, 12, 0, 0)
    agg = dt.datetime(2026, 5, 13, 12, 0, 0)
    assert compute_lead_hours(us, agg) == 13 * 24.0
    assert compute_lead_hours(us, None) is None
    assert compute_lead_hours(None, agg) is None


def test_lead_metric_recorded_via_pipeline(db_env):
    from aiapiradar.pipeline.pipeline import Pipeline
    from aiapiradar.pipeline.classify import HeuristicClassifier
    from aiapiradar.core.signal import Signal
    from aiapiradar.db import get_db

    pipe = Pipeline(classifier=HeuristicClassifier())
    t0 = dt.datetime(2026, 4, 30, 12, 0, 0, tzinfo=dt.timezone.utc)
    t1 = dt.datetime(2026, 5, 13, 12, 0, 0, tzinfo=dt.timezone.utc)
    # we discover it first (forum), aggregator (telegram) sees it later
    ours = Signal(source="nodeseek", raw_text="freemodel.dev $300 free credits register",
                  url="https://freemodel.dev", source_url="https://nodeseek.com/p/1", observed_at=t0)
    agg = Signal(source="telegram", raw_text="freemodel.dev $300 free credits register",
                 url="https://freemodel.dev", source_url="https://t.me/c/1", observed_at=t1)
    pipe.process_signals([ours, agg])

    with get_db() as db:
        offers = db.execute("SELECT id FROM offers")
        assert len(offers) == 1
        lms = db.execute(
            "SELECT first_seen_by_us, first_seen_in_aggregator, lead_hours "
            "FROM lead_metrics WHERE offer_id = ?",
            [offers[0]["id"]],
        )
        assert len(lms) == 1
        lm = lms[0]
        assert lm["first_seen_by_us"] is not None
        assert lm["first_seen_in_aggregator"] is not None
        assert lm["lead_hours"] == 13 * 24.0  # we were 13 days earlier


# --- notifier --------------------------------------------------------------
def test_notifier_sends_once(db_env, monkeypatch):
    import aiapiradar.config as config

    monkeypatch.setenv("AIRADAR_TG_BOT_TOKEN", "test-token")
    monkeypatch.setenv("AIRADAR_TG_CHAT_ID", "123")
    monkeypatch.setenv("AIRADAR_NOTIFY_MIN_SCORE", "0.6")
    # db_env already populated the settings cache during init_db (before these
    # TG vars existed); clear it so the notifier reads the now-set credentials.
    config.get_settings.cache_clear()

    from aiapiradar.models import utcnow
    from tests.factories import make_offer, make_service

    svc = make_service("freemodel.dev", name="FreeModel", type="relay", status="active")
    make_offer(svc, type="relay", amount=300, currency="USD", models=["gpt"],
               score=0.9, first_seen_at=utcnow())    # above threshold
    make_offer(svc, type="saas_trial", amount=5, score=0.2,
               first_seen_at=utcnow())               # below threshold

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


def test_notifier_disabled_without_token(db_env, monkeypatch):
    import aiapiradar.config as config

    monkeypatch.delenv("AIRADAR_TG_BOT_TOKEN", raising=False)
    monkeypatch.delenv("AIRADAR_TG_CHAT_ID", raising=False)
    config.get_settings.cache_clear()
    from aiapiradar.notifier import notify_new_offers
    assert asyncio.run(notify_new_offers()) == 0

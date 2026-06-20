"""Phase 7 tests: telegram ingest builder + disabled no-op; youtube parse +
disabled no-op; telegram signal counts as aggregator in lead metrics."""
from __future__ import annotations

import asyncio
import datetime as dt

from aiapiradar.collectors import get_registry, load_builtin
from aiapiradar.collectors.telegram import TelegramCollector, build_signal
from aiapiradar.collectors.youtube import YouTubeCollector, parse_search


def test_phase7_collectors_register():
    load_builtin()
    assert {"telegram", "youtube"} <= set(get_registry())


def test_telegram_build_signal():
    sig = build_signal("free $50 api credits", "asati_shill", 412,
                       dt.datetime(2026, 6, 20, tzinfo=dt.timezone.utc))
    assert sig.source == "telegram"
    assert sig.source_url == "https://t.me/asati_shill/412"
    assert sig.meta["channel"] == "asati_shill"


def test_telegram_disabled_without_creds(monkeypatch):
    monkeypatch.delenv("AIRADAR_TG_API_ID", raising=False)
    monkeypatch.delenv("AIRADAR_TG_API_HASH", raising=False)
    import aiapiradar.config as config
    config.get_settings.cache_clear()
    assert TelegramCollector.configured() is False
    assert list(asyncio.run(TelegramCollector().collect())) == []


def test_youtube_parse():
    data = {"items": [
        {"id": {"videoId": "abc123"},
         "snippet": {"title": "How to get free AI API credits", "description": "guide"}},
        {"id": {"kind": "channel"}, "snippet": {"title": "no video id"}},
    ]}
    sigs = parse_search(data)
    assert len(sigs) == 1
    assert sigs[0].url == "https://youtu.be/abc123"


def test_youtube_disabled_without_key(monkeypatch):
    monkeypatch.delenv("AIRADAR_YOUTUBE_API_KEY", raising=False)
    import aiapiradar.config as config
    config.get_settings.cache_clear()
    assert list(asyncio.run(YouTubeCollector().collect())) == []


def test_telegram_signal_is_aggregator_in_lead_metric(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRADAR_DB_URL", f"sqlite:///{tmp_path / 'p7.db'}")
    import aiapiradar.config as config
    import aiapiradar.db as db
    config.get_settings.cache_clear()
    db._engine = None
    db._SessionFactory = None
    db.init_db()

    from aiapiradar.pipeline.pipeline import Pipeline
    from aiapiradar.pipeline.classify import HeuristicClassifier
    from aiapiradar.models import LeadMetric, Offer

    tg = build_signal("freemodel.dev $300 free credits register https://freemodel.dev",
                      "kyloai", 1, dt.datetime(2026, 5, 13, tzinfo=dt.timezone.utc))
    Pipeline(classifier=HeuristicClassifier()).process_signals([tg])

    with db.session_scope() as s:
        offer = s.query(Offer).one()
        lm = s.query(LeadMetric).filter_by(offer_id=offer.id).one()
        assert lm.first_seen_in_aggregator is not None
        assert lm.first_seen_by_us is None   # only aggregator saw it

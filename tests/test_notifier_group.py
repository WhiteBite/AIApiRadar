"""Group-mode (forum-topic) notifier test over the raw-SQL path.

Exercises both routing branches: a high-score AI-service offer (format_offer →
AI topic) and a telegram-sourced offer (format_forwarded → forwarded topic).
Network is stubbed with httpx.MockTransport so the test is deterministic/offline.
"""
from __future__ import annotations

import asyncio

import httpx

from aiapiradar.config import Settings
from aiapiradar.db import get_db
from aiapiradar.models import utcnow
from aiapiradar.notifier import notify_new_offers
from tests.factories import make_offer, make_service, make_signal


def _set_topic(offer_id: int, topic: str) -> None:
    with get_db() as db:
        db.run("UPDATE offers SET topic=? WHERE id=?", [topic, offer_id])


def test_group_notifier_sends_and_marks(db_env):
    svc = make_service("freemodel.dev", name="FreeModel", type="relay", status="active")

    # 1) Plain AI-service offer → format_offer / AI topic.
    ai_offer = make_offer(svc, type="relay", amount=300, currency="USD",
                          models=["gpt"], score=0.9, url="https://freemodel.dev",
                          first_seen_at=utcnow())
    _set_topic(ai_offer, "ai_service")
    make_signal(offer_id=ai_offer, service_id=svc, source="nodeseek",
                source_url="https://nodeseek.com/p/1",
                raw_text="freemodel.dev $300 free credits register")

    # 2) Telegram-sourced offer → format_forwarded / forwarded topic.
    tg_offer = make_offer(svc, type="saas_promo", amount=50, currency="USD",
                          score=0.8, url="https://freemodel.dev/tg",
                          first_seen_at=utcnow())
    make_signal(offer_id=tg_offer, service_id=svc, source="telegram",
                source_url="https://t.me/somechan/1",
                raw_text="hot deal repost from somechan")

    settings = Settings(
        _env_file=None,
        tg_bot_token="x",
        tg_group_chat_id="-100123",
        tg_topic_ai_services=1,
        tg_topic_freebies=2,
        tg_topic_forwarded=3,
        notify_min_score=0.0,
        notify_min_confidence=0.0,
    )

    sent_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent_urls.append(str(request.url))
        if "createForumTopic" in str(request.url):
            return httpx.Response(200, json={"ok": True,
                                             "result": {"message_thread_id": 1}})
        return httpx.Response(200, json={"ok": True,
                                        "result": {"message_thread_id": 1}})

    async def run() -> int:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await notify_new_offers(limit=10, client=client, settings=settings)

    sent = asyncio.run(run())

    assert sent == 2
    assert len(sent_urls) == 2
    assert all("sendMessage" in u for u in sent_urls)

    with get_db() as db:
        rows = db.execute(
            "SELECT id, notified_at FROM offers ORDER BY id",
        )
        assert len(rows) == 2
        assert all(r["notified_at"] is not None for r in rows)

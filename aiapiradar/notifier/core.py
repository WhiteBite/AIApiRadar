"""Notifier entry points: single-chat and group (forum-topic) modes."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

import httpx

from ..config import Settings, get_settings
from ..db.base import get_db, json_decode
from ..logging_conf import get_logger
from ..models import utcnow
from ..util.dtutil import to_storage_str
from .client import send_telegram, send_to_topic
from .format import (
    format_forwarded,
    format_offer,
    offer_confidence,
    route_topic,
    telegram_channel,
)
from .topics import ensure_group_topics

log = get_logger("notifier")


# ── Read-only view builders ─────────────────────────────────────────────────
def _build_views(db, rows):
    """Turn raw offer rows into (offer_view, service_view, offer_id) tuples.

    The views expose exactly the attributes the formatters read, so format.py
    logic stays unchanged while the data now comes from raw SQL.
    """
    views = []
    for row in rows:
        offer_id = row["id"]
        sig_rows = db.execute(
            "SELECT source, source_url, raw_text, confidence "
            "FROM signals WHERE offer_id = ?",
            [offer_id],
        )
        signals = [
            SimpleNamespace(
                source=s["source"],
                source_url=s["source_url"],
                raw_text=s["raw_text"],
                confidence=s["confidence"],
            )
            for s in sig_rows
        ]
        offer = SimpleNamespace(
            url=row["url"],
            currency=row["currency"],
            amount=row["amount"],
            effort=row["effort"],
            type=row["type"],
            score=row["score"],
            models=json_decode(row["models"]) or [],
            referral_required=row["referral_required"],
            claim_steps=row["claim_steps"],
            description=row["description"],
            requirements=row["requirements"],
            topic=row["topic"],
            signals=signals,
        )
        service = SimpleNamespace(canonical_domain=row["canonical_domain"])
        views.append((offer, service, offer_id))
    return views


# ── Entry points ───────────────────────────────────────────────────────────
async def notify_new_offers(limit: int = 20, client: Optional[httpx.AsyncClient] = None,
                            settings: Optional[Settings] = None) -> int:
    settings = settings or get_settings()
    if settings.tg_bot_token and settings.tg_group_chat_id:
        return await _notify_group(limit, client, settings)
    return await _notify_single(limit, client, settings)


async def _notify_single(limit: int, client: Optional[httpx.AsyncClient],
                         settings: Settings) -> int:
    if not (settings.tg_bot_token and settings.tg_chat_id):
        log.info("notifier disabled (no tg token/chat configured)")
        return 0

    own_client = client or httpx.AsyncClient(timeout=20.0)
    sent = 0
    try:
        with get_db() as db:
            rows = db.execute(
                "SELECT o.*, s.canonical_domain FROM offers o "
                "JOIN services s ON o.service_id = s.id "
                "WHERE o.notified_at IS NULL AND o.score >= ? "
                "ORDER BY o.score DESC LIMIT ?",
                [settings.notify_min_score, limit],
            )
            for offer, service, offer_id in _build_views(db, rows):
                if await send_telegram(format_offer(offer, service), own_client,
                                       settings.tg_bot_token, settings.tg_chat_id):
                    db.run("UPDATE offers SET notified_at=? WHERE id=?",
                           [to_storage_str(utcnow()), offer_id])
                    sent += 1
    finally:
        if client is None:
            await own_client.aclose()
    log.info("notifier sent %d offers", sent)
    return sent


async def _notify_group(limit: int, client: Optional[httpx.AsyncClient],
                        settings: Settings) -> int:
    own_client = client or httpx.AsyncClient(timeout=20.0)
    sent = 0
    try:
        topics = await ensure_group_topics(own_client, settings)
        with get_db() as db:
            # Fetch a generous candidate window, then apply the python-side
            # (score+confidence) OR (from-telegram) gate.
            rows = db.execute(
                "SELECT o.*, s.canonical_domain FROM offers o "
                "JOIN services s ON o.service_id = s.id "
                "WHERE o.notified_at IS NULL "
                "ORDER BY o.score DESC LIMIT ?",
                [max(limit * 5, 25)],
            )
            for offer, service, offer_id in _build_views(db, rows):
                if sent >= limit:
                    break
                channel = telegram_channel(offer)
                from_tg = channel is not None
                plausible = (offer.score >= settings.notify_min_score
                             and offer_confidence(offer) >= settings.notify_min_confidence)
                if not (from_tg or plausible):
                    continue
                cat = route_topic(offer, service, from_tg)
                thread_id = topics.get(cat)
                text = (format_forwarded(offer, service, channel) if from_tg
                        else format_offer(offer, service))
                if await send_to_topic(text, own_client, settings.tg_bot_token,
                                       settings.tg_group_chat_id, thread_id):
                    db.run("UPDATE offers SET notified_at=? WHERE id=?",
                           [to_storage_str(utcnow()), offer_id])
                    sent += 1
    finally:
        if client is None:
            await own_client.aclose()
    log.info("group notifier sent %d offers", sent)
    return sent

"""Notifier entry points: single-chat and group (forum-topic) modes."""
from __future__ import annotations

from typing import Optional

import httpx
from sqlalchemy import select

from ..config import Settings, get_settings
from ..db import session_scope
from ..logging_conf import get_logger
from ..models import Offer, Service, utcnow
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
        with session_scope() as session:
            rows = session.execute(
                select(Offer, Service).join(Service, Offer.service_id == Service.id)
                .where(Offer.notified_at.is_(None), Offer.score >= settings.notify_min_score)
                .order_by(Offer.score.desc()).limit(limit)
            ).all()
            for offer, service in rows:
                if await send_telegram(format_offer(offer, service), own_client,
                                       settings.tg_bot_token, settings.tg_chat_id):
                    offer.notified_at = utcnow()
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
        with session_scope() as session:
            # Fetch a generous candidate window, then apply the python-side
            # (score+confidence) OR (from-telegram) gate.
            rows = session.execute(
                select(Offer, Service).join(Service, Offer.service_id == Service.id)
                .where(Offer.notified_at.is_(None))
                .order_by(Offer.score.desc()).limit(max(limit * 5, 25))
            ).all()
            for offer, service in rows:
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
                    offer.notified_at = utcnow()
                    sent += 1
    finally:
        if client is None:
            await own_client.aclose()
    log.info("group notifier sent %d offers", sent)
    return sent

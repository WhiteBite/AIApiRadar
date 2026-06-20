"""Notifier: push fresh, high-score offers to Telegram.

Sends each qualifying Offer once (tracked via Offer.notified_at). Disabled
gracefully when no bot token / chat id is configured. Network goes through an
injectable httpx.AsyncClient so tests use MockTransport.
"""
from __future__ import annotations

from typing import Optional

import httpx
from sqlalchemy import select

from .config import Settings, get_settings
from .db import session_scope
from .logging_conf import get_logger
from .models import Offer, Service, utcnow

log = get_logger("notifier")


def format_offer(offer: Offer, service: Optional[Service]) -> str:
    head = service.canonical_domain if service else (offer.url or "offer")
    amt = f"{offer.currency or '$'}{int(offer.amount)}" if offer.amount else "?"
    lines = [
        f"\U0001F7E2 {head}",
        f"\U0001F4B0 {amt} \u00b7 {offer.type} \u00b7 score {offer.score:.2f}",
    ]
    if offer.models:
        lines.append("\U0001F916 " + ", ".join(offer.models))
    if offer.referral_required:
        lines.append("\u26A0 referral required")
    if offer.claim_steps:
        lines.append(offer.claim_steps[:300])
    if offer.url:
        lines.append(offer.url)
    return "\n".join(lines)


async def send_telegram(text: str, client: httpx.AsyncClient, token: str, chat_id: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = await client.post(url, json={
            "chat_id": chat_id, "text": text, "disable_web_page_preview": True,
        })
        return r.status_code == 200
    except Exception:
        log.warning("telegram send failed", exc_info=False)
        return False


async def notify_new_offers(limit: int = 20, client: Optional[httpx.AsyncClient] = None,
                            settings: Optional[Settings] = None) -> int:
    settings = settings or get_settings()
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

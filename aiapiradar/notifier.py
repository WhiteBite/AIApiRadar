"""Notifier: push fresh, high-score offers to Telegram.

Two modes, picked automatically:

  * group mode  — when `tg_group_chat_id` is set, posts into forum TOPICS of a
    supergroup. Offers are routed to one of three topics (AI services /
    freebies / forwarded-from-other-channels) and filtered by an AI gate
    (score + confidence) OR by having come from another telegram channel.
  * legacy mode — when only `tg_chat_id` is set, posts every qualifying offer
    into a single chat (the original behaviour).

Each qualifying Offer is sent once (tracked via Offer.notified_at). Disabled
gracefully when no bot token / destination is configured. Network goes through
an injectable httpx.AsyncClient so tests use MockTransport.
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

# ── Forum topic taxonomy ───────────────────────────────────────────────────
TOPIC_AI = "ai_services"
TOPIC_FREEBIE = "freebies"
TOPIC_FORWARDED = "forwarded"

TOPIC_TITLES = {
    TOPIC_AI: "\U0001F916 ИИ-сервисы и агенты",
    TOPIC_FREEBIE: "\U0001F381 Халява и акции",
    TOPIC_FORWARDED: "\U0001F4E1 Из других каналов",
}
# Telegram forum icon colours (optional, cosmetic).
TOPIC_ICON_COLORS = {
    TOPIC_AI: 7322096,       # blue
    TOPIC_FREEBIE: 16766590,  # gold
    TOPIC_FORWARDED: 13338331,  # purple
}

# Keywords that mark an offer as "freebie / promo / infra" rather than an
# AI-service proper → routed to the 🎁 topic.
_FREEBIE_KEYWORDS = (
    "vds", "vps", "vpn", "хостинг", "hosting", "сервер", "server", "домен",
    "domain", "ssl", "диск", "storage", "облак", "cloud credit", "free tier",
    "бесплатн", "халяв", "промокод", "promo code", "coupon", "купон", "скидк",
)


# ── Telegram Bot API plumbing ──────────────────────────────────────────────
async def _tg_request(method: str, payload: dict, client: httpx.AsyncClient,
                      token: str) -> tuple[bool, dict]:
    """Call one Bot API method. Returns (ok, result_dict).

    Tolerant of mock transports that return `{"ok": true}` without a `result`.
    """
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        r = await client.post(url, json=payload)
    except Exception:
        log.warning("telegram %s error", method, exc_info=False)
        return False, {}
    try:
        data = r.json()
    except Exception:
        data = {}
    ok = r.status_code == 200 and bool(data.get("ok", True))
    if not ok:
        log.warning("telegram %s failed: status=%s body=%s", method, r.status_code, data)
    return ok, (data.get("result") or {})


async def send_telegram(text: str, client: httpx.AsyncClient, token: str, chat_id: str) -> bool:
    """Legacy single-chat send (kept for backward compatibility)."""
    ok, _ = await _tg_request("sendMessage", {
        "chat_id": chat_id, "text": text, "disable_web_page_preview": True,
    }, client, token)
    return ok


async def send_to_topic(text: str, client: httpx.AsyncClient, token: str,
                        chat_id: str, thread_id: Optional[int]) -> bool:
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if thread_id:
        payload["message_thread_id"] = int(thread_id)
    ok, _ = await _tg_request("sendMessage", payload, client, token)
    return ok


async def create_forum_topic(name: str, chat_id: str, client: httpx.AsyncClient,
                             token: str, icon_color: Optional[int] = None) -> Optional[int]:
    payload: dict = {"chat_id": chat_id, "name": name}
    if icon_color:
        payload["icon_color"] = icon_color
    ok, result = await _tg_request("createForumTopic", payload, client, token)
    tid = result.get("message_thread_id")
    if ok and tid:
        return int(tid)
    return None


# ── Formatting ─────────────────────────────────────────────────────────────
def format_offer(offer: Offer, service: Optional[Service]) -> str:
    head = service.canonical_domain if service else (offer.url or "offer")
    amt = f"{offer.currency or '$'}{int(offer.amount)}" if offer.amount else "?"
    effort = f" \u00b7 {offer.effort}" if offer.effort else ""
    lines = [
        f"\U0001F7E2 {head}",
        f"\U0001F4B0 {amt} \u00b7 {offer.type}{effort} \u00b7 score {offer.score:.2f}",
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


def _best_text(offer: Offer) -> str:
    texts = [s.raw_text for s in offer.signals if s.raw_text]
    return max(texts, key=len) if texts else ""


def format_forwarded(offer: Offer, service: Optional[Service], channel: Optional[str]) -> str:
    """Repost of a message picked up from another telegram channel.

    The bot can't natively forward (the channels are read via a user client it
    isn't a member of), so we repost the text with attribution + source link.
    """
    head = f"\U0001F4E1 из @{channel}" if channel else "\U0001F4E1 из другого канала"
    body = (_best_text(offer) or offer.description or offer.claim_steps or "").strip()
    lines = [head, "", body[:3500]]
    link = _source_url(offer)
    if link:
        lines += ["", link]
    return "\n".join(l for l in lines if l is not None)


# ── Offer inspection helpers ───────────────────────────────────────────────
def _channel_from_url(url: Optional[str]) -> Optional[str]:
    if url and "t.me/" in url:
        rest = url.split("t.me/", 1)[1]
        return rest.split("/", 1)[0] or None
    return None


def _source_url(offer: Offer) -> Optional[str]:
    for sig in offer.signals:
        if sig.source_url:
            return sig.source_url
    return None


def telegram_channel(offer: Offer) -> Optional[str]:
    """Channel name if any signal came from a telegram channel, else None."""
    for sig in offer.signals:
        if (sig.source or "").startswith("telegram"):
            return _channel_from_url(sig.source_url) or "канал"
    return None


def offer_confidence(offer: Offer) -> float:
    vals = [s.confidence for s in offer.signals if s.confidence is not None]
    return max(vals) if vals else 0.0


def route_topic(offer: Offer, service: Optional[Service], from_telegram: bool) -> str:
    if from_telegram:
        return TOPIC_FORWARDED
    # Prefer the classifier's topic (LLM or heuristic) when present.
    topic = (offer.topic or "").strip()
    if topic == "ai_service":
        return TOPIC_AI
    if topic == "freebie":
        return TOPIC_FREEBIE
    # Fallback: rule-based routing for offers classified before `topic` existed.
    blob = " ".join(filter(None, [
        service.canonical_domain if service else "",
        offer.description or "",
        offer.claim_steps or "",
        offer.requirements or "",
        " ".join(offer.models or []),
    ])).lower()
    if offer.type in ("saas_promo", "grant") or any(k in blob for k in _FREEBIE_KEYWORDS):
        return TOPIC_FREEBIE
    return TOPIC_AI


# ── Topic provisioning ─────────────────────────────────────────────────────
async def ensure_group_topics(client: httpx.AsyncClient, settings: Settings) -> dict[str, int]:
    """Resolve {category: message_thread_id}, creating + persisting any missing.

    Resolution order per category: env override → persisted map → create now.
    Created ids are written back to the persisted map so we never duplicate
    topics across runs.
    """
    from .sources import get_tg_topic_map, save_tg_topic_map

    env_map = {
        TOPIC_AI: settings.tg_topic_ai_services,
        TOPIC_FREEBIE: settings.tg_topic_freebies,
        TOPIC_FORWARDED: settings.tg_topic_forwarded,
    }
    stored = dict(get_tg_topic_map())
    resolved: dict[str, int] = {}
    dirty = False
    for cat in (TOPIC_AI, TOPIC_FREEBIE, TOPIC_FORWARDED):
        tid = env_map.get(cat) or stored.get(cat)
        if not tid:
            tid = await create_forum_topic(
                TOPIC_TITLES[cat], settings.tg_group_chat_id, client,
                settings.tg_bot_token, TOPIC_ICON_COLORS.get(cat),
            )
            if tid:
                stored[cat] = tid
                dirty = True
                log.info("created forum topic %s -> %s", cat, tid)
            else:
                log.warning("could not create forum topic %s (bot admin + topics on?)", cat)
        if tid:
            resolved[cat] = int(tid)
    if dirty:
        try:
            save_tg_topic_map(stored)
        except Exception:
            log.warning("failed to persist tg topic map", exc_info=False)
    return resolved


async def setup_group_topics(settings: Optional[Settings] = None) -> dict[str, int]:
    """One-shot: ensure the forum topics exist and print their ids (cli tg-setup)."""
    settings = settings or get_settings()
    if not (settings.tg_bot_token and settings.tg_group_chat_id):
        log.info("tg-setup skipped (no tg_bot_token / tg_group_chat_id)")
        return {}
    async with httpx.AsyncClient(timeout=20.0) as client:
        topics = await ensure_group_topics(client, settings)
    for cat in (TOPIC_AI, TOPIC_FREEBIE, TOPIC_FORWARDED):
        print(f"{cat:12} {TOPIC_TITLES[cat]:28} message_thread_id={topics.get(cat, '-')}")
    return topics


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

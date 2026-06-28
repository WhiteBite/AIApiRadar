"""Message formatting, offer inspection helpers, and topic taxonomy."""
from __future__ import annotations

from typing import Optional

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


# ── Formatting ─────────────────────────────────────────────────────────────
def format_offer(offer, service) -> str:
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


def _best_text(offer) -> str:
    texts = [s.raw_text for s in offer.signals if s.raw_text]
    return max(texts, key=len) if texts else ""


def format_forwarded(offer, service, channel: Optional[str]) -> str:
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


def _source_url(offer) -> Optional[str]:
    for sig in offer.signals:
        if sig.source_url:
            return sig.source_url
    return None


def telegram_channel(offer) -> Optional[str]:
    """Channel name if any signal came from a telegram channel, else None."""
    for sig in offer.signals:
        if (sig.source or "").startswith("telegram"):
            return _channel_from_url(sig.source_url) or "канал"
    return None


def offer_confidence(offer) -> float:
    vals = [s.confidence for s in offer.signals if s.confidence is not None]
    return max(vals) if vals else 0.0


def route_topic(offer, service, from_telegram: bool) -> str:
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

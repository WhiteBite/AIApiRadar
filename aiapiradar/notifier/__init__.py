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

This package was split out of the former single-module ``notifier.py``. The
re-exports below preserve the original public surface so that
``from aiapiradar.notifier import X`` keeps working unchanged.
"""
from __future__ import annotations

from ..logging_conf import get_logger
from .client import (
    _tg_request,
    create_forum_topic,
    send_telegram,
    send_to_topic,
)
from .core import _notify_group, _notify_single, notify_new_offers
from .format import (
    _FREEBIE_KEYWORDS,
    _best_text,
    _channel_from_url,
    _source_url,
    TOPIC_AI,
    TOPIC_FORWARDED,
    TOPIC_FREEBIE,
    TOPIC_ICON_COLORS,
    TOPIC_TITLES,
    format_forwarded,
    format_offer,
    offer_confidence,
    route_topic,
    telegram_channel,
)
from .topics import ensure_group_topics, setup_group_topics

log = get_logger("notifier")

__all__ = [
    # client
    "_tg_request",
    "send_telegram",
    "send_to_topic",
    "create_forum_topic",
    # format / routing
    "format_offer",
    "format_forwarded",
    "_best_text",
    "_channel_from_url",
    "_source_url",
    "telegram_channel",
    "offer_confidence",
    "route_topic",
    "TOPIC_AI",
    "TOPIC_FREEBIE",
    "TOPIC_FORWARDED",
    "TOPIC_TITLES",
    "TOPIC_ICON_COLORS",
    "_FREEBIE_KEYWORDS",
    # topics
    "ensure_group_topics",
    "setup_group_topics",
    # core
    "notify_new_offers",
    "_notify_single",
    "_notify_group",
    "log",
]

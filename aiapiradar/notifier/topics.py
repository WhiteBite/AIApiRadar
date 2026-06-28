"""Forum-topic provisioning for the group-mode notifier."""
from __future__ import annotations

from typing import Optional

import httpx

from ..config import Settings, get_settings
from ..logging_conf import get_logger
from .client import create_forum_topic
from .format import (
    TOPIC_AI,
    TOPIC_FORWARDED,
    TOPIC_FREEBIE,
    TOPIC_ICON_COLORS,
    TOPIC_TITLES,
)

log = get_logger("notifier")


# ── Topic provisioning ─────────────────────────────────────────────────────
async def ensure_group_topics(client: httpx.AsyncClient, settings: Settings) -> dict[str, int]:
    """Resolve {category: message_thread_id}, creating + persisting any missing.

    Resolution order per category: env override → persisted map → create now.
    Created ids are written back to the persisted map so we never duplicate
    topics across runs.
    """
    from ..sources import get_tg_topic_map, save_tg_topic_map

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

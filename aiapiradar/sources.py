"""Source management — DB-backed list of what to monitor.

Used by:
  - the API (CRUD endpoints) so users configure sources from the frontend
  - collectors (telegram reads its channel list from here)

Platform-agnostic via the Database protocol (works on SQLite and D1).

A telegram source stores config like:
    {"channel": "valencylab", "topic_id": 5}   # specific forum topic
    {"channel": "asati_shill"}                  # whole channel
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from .db import get_db
from .db.base import json_decode, json_encode
from .logging_conf import get_logger

log = get_logger("sources")


def _row_to_dict(r: dict) -> dict:
    r = dict(r)
    r["config"] = json_decode(r.get("config")) or {}
    r["enabled"] = bool(r.get("enabled"))
    return r


def list_sources(type: Optional[str] = None) -> list[dict]:
    with get_db() as db:
        if type:
            rows = db.execute(
                "SELECT * FROM sources WHERE type = ? ORDER BY id", [type]
            )
        else:
            rows = db.execute("SELECT * FROM sources ORDER BY type, id")
    return [_row_to_dict(r) for r in rows]


def get_source(source_id: int) -> Optional[dict]:
    with get_db() as db:
        rows = db.execute("SELECT * FROM sources WHERE id = ?", [source_id])
    return _row_to_dict(rows[0]) if rows else None


def create_source(
    type: str, name: str, config: Optional[dict] = None, enabled: bool = True
) -> int:
    with get_db() as db:
        # Upsert-by-name to avoid UNIQUE collisions on re-add.
        existing = db.execute("SELECT id FROM sources WHERE name = ?", [name])
        if existing:
            sid = existing[0]["id"]
            db.run(
                "UPDATE sources SET type=?, config=?, enabled=? WHERE id=?",
                [type, json_encode(config), int(enabled), sid],
            )
        else:
            db.run(
                "INSERT INTO sources (name, type, enabled, config) VALUES (?, ?, ?, ?)",
                [name, type, int(enabled), json_encode(config)],
            )
            sid = db.execute("SELECT last_insert_rowid() AS id")[0]["id"]
        db.commit()
    log.info("source upserted: %s (%s)", name, type)
    return sid


def update_source(
    source_id: int,
    *,
    enabled: Optional[bool] = None,
    config: Optional[dict] = None,
    name: Optional[str] = None,
) -> bool:
    sets, params = [], []
    if enabled is not None:
        sets.append("enabled=?"); params.append(int(enabled))
    if config is not None:
        sets.append("config=?"); params.append(json_encode(config))
    if name is not None:
        sets.append("name=?"); params.append(name)
    if not sets:
        return False
    params.append(source_id)
    with get_db() as db:
        db.run(f"UPDATE sources SET {', '.join(sets)} WHERE id=?", params)
        db.commit()
    return True


def delete_source(source_id: int) -> bool:
    with get_db() as db:
        db.run("DELETE FROM sources WHERE id = ?", [source_id])
        db.commit()
    return True


def mark_run(name: str, signals_count: Optional[int] = None) -> None:
    """Record that a source ran (for the Sources page status)."""
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    with get_db() as db:
        db.run("UPDATE sources SET last_run=? WHERE name=?", [now, name])
        db.commit()


# ── Telegram group (forum) topic map ──────────────────────────────────────
# A single config row persists the auto-created forum topic ids so we don't
# recreate (and duplicate) topics on every notify run. Stored as type
# "tg_config", name "__tg_topics__", config = {category: message_thread_id}.
TG_TOPICS_SOURCE = "__tg_topics__"


def get_tg_topic_map() -> dict[str, int]:
    """Return the persisted {category: message_thread_id} map (empty if unset)."""
    try:
        for s in list_sources("tg_config"):
            if s["name"] == TG_TOPICS_SOURCE:
                cfg = s.get("config") or {}
                return {k: int(v) for k, v in cfg.items() if v}
    except Exception:
        log.warning("could not read tg topic map", exc_info=False)
    return {}


def save_tg_topic_map(mapping: dict[str, int]) -> None:
    """Persist the {category: message_thread_id} map (upsert by name)."""
    clean = {k: int(v) for k, v in mapping.items() if v}
    create_source(type="tg_config", name=TG_TOPICS_SOURCE, config=clean, enabled=True)


def enabled_telegram_channels() -> list[dict[str, Any]]:
    """Return [{"channel": str, "topic_id": int|None}] for enabled telegram sources."""
    out: list[dict[str, Any]] = []
    for s in list_sources("telegram"):
        if not s["enabled"]:
            continue
        cfg = s["config"] or {}
        ch = cfg.get("channel")
        if ch:
            out.append({"channel": ch, "topic_id": cfg.get("topic_id")})
    return out

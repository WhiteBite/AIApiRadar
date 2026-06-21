"""Source ↔ runner configuration layer.

Bridges the collector registry (code) and the `sources` DB table (runtime
config). Lets an operator enable/disable collectors and override their polling
interval without touching code — both the long-lived APScheduler runner and the
one-shot batch runner consult this layer to decide what to run and how often.

All DB access goes through the platform-agnostic `Database` protocol via
`get_db()` — never SQLAlchemy directly — so this works on SQLite (VDS) and
Cloudflare D1 alike.

`sources` columns: (id, name, type, enabled, last_run, config)
  - enabled : INTEGER (0/1)
  - config  : JSON string (object). Recognised key: "interval" (seconds).
"""
from __future__ import annotations

from typing import Dict, Optional, Type

from ..db import get_db
from ..db.base import json_decode, json_encode
from ..logging_conf import get_logger

log = get_logger("source_config")


def sync_sources(registry: Dict[str, Type]) -> None:
    """Ensure every registered collector has a row in `sources`.

    Idempotent: relies on the UNIQUE(name) constraint and INSERT OR IGNORE, so
    re-running it never duplicates rows or clobbers an operator's edits
    (enabled flag, interval override) on existing rows.
    """
    with get_db() as db:
        for name, cls in registry.items():
            db.run(
                "INSERT OR IGNORE INTO sources (name, type, enabled, config) "
                "VALUES (?, ?, 1, ?)",
                [name, getattr(cls, "kind", "generic"), json_encode({})],
            )
        db.commit()


def get_source_config(name: str) -> dict:
    """Return the runtime config for a single collector.

    Shape: ``{"enabled": bool, "interval": int | None, "config": dict}``.
    If the collector has no row yet, returns sane defaults (enabled, no
    interval override). ``interval`` is pulled from ``config["interval"]`` when
    present so an operator can override the per-collector cadence via the
    config JSON alone.
    """
    with get_db() as db:
        rows = db.execute(
            "SELECT enabled, config FROM sources WHERE name = ?", [name]
        )

    if not rows:
        return {"enabled": True, "interval": None, "config": {}}

    row = rows[0]
    cfg = json_decode(row.get("config")) or {}
    if not isinstance(cfg, dict):
        cfg = {}

    interval = cfg.get("interval")
    if interval is not None:
        try:
            interval = int(interval)
        except (TypeError, ValueError):
            interval = None

    return {
        "enabled": bool(row.get("enabled", 1)),
        "interval": interval,
        "config": cfg,
    }


def resolve_interval(name: str, cls: Type) -> int:
    """Effective polling interval for a collector.

    Precedence: ``sources.config["interval"]`` (operator override) > the
    collector class's declared ``interval`` > the 900s fallback.
    """
    override = get_source_config(name).get("interval")
    if override is not None:
        return override
    return getattr(cls, "interval", 900)


def enabled_collectors(registry: Dict[str, Type]) -> Dict[str, Type]:
    """Filter the registry down to collectors whose `sources.enabled=1`.

    Reads all source rows once (cheap) rather than querying per collector.
    Collectors without a row are treated as enabled (the default), matching
    `get_source_config` — so a brand-new collector runs even before
    `sync_sources` has persisted its row.
    """
    with get_db() as db:
        rows = db.execute("SELECT name, enabled FROM sources")
    disabled = {r["name"] for r in rows if not bool(r.get("enabled", 1))}
    return {name: cls for name, cls in registry.items() if name not in disabled}

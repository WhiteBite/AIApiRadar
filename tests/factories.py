"""Ergonomic row factories over the raw-SQL ``Database`` protocol.

These replace the SQLAlchemy ORM object construction (``Service(...)``,
``Offer(...)``, ``Signal(...)``) used in the legacy tests. Each factory opens
its own ``get_db()`` connection, inserts a single row with sensible defaults,
and returns the new row id — so a test only passes the columns it cares about.

This is the same data path BOTH production targets run (SQLite locally / VPS,
D1 on Cloudflare): every write goes through ``db.run`` with an explicit column
list, JSON-encoding list/dict columns via ``json_encode``.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from aiapiradar.db import get_db
from aiapiradar.db.base import json_encode
from aiapiradar.util.dtutil import to_storage_str


def _dt(value: Any) -> Any:
    """Normalize a datetime to the canonical storage string; pass strings through."""
    if isinstance(value, dt.datetime):
        return to_storage_str(value)
    return value


def _insert(table: str, values: dict[str, Any]) -> int:
    """Insert a row from {column: value}, dropping None values so NOT NULL columns
    fall back to their schema defaults, and return the new row id."""
    cols = [c for c, v in values.items() if v is not None]
    params = [values[c] for c in cols]
    placeholders = ", ".join("?" for _ in cols)
    collist = ", ".join(cols)
    with get_db() as db:
        db.run(f"INSERT INTO {table} ({collist}) VALUES ({placeholders})", params)
        rows = db.execute("SELECT last_insert_rowid() AS id")
        return int(rows[0]["id"])


def make_service(
    canonical_domain: str,
    *,
    name: Optional[str] = None,
    type: str = "relay",
    engine: Optional[str] = None,
    status: str = "new",
    reliability: float = 0.0,
    models: Optional[list] = None,
    domain_first_seen: Any = None,
) -> int:
    """Insert a ``services`` row, return its id."""
    return _insert(
        "services",
        {
            "canonical_domain": canonical_domain,
            "name": name,
            "type": type,
            "engine": engine,
            "status": status,
            "reliability": reliability,
            "models": json_encode(models),
            "domain_first_seen": _dt(domain_first_seen),
        },
    )


def make_offer(
    service_id: int,
    *,
    type: str = "saas_trial",
    amount: Optional[float] = None,
    currency: Optional[str] = None,
    models: Optional[list] = None,
    effort: Optional[str] = None,
    unit: Optional[str] = None,
    referral_required: bool = False,
    status: str = "new",
    score: float = 0.0,
    url: Optional[str] = None,
    first_seen_at: Any = None,
    conditions: Optional[dict] = None,
) -> int:
    """Insert an ``offers`` row, return its id."""
    return _insert(
        "offers",
        {
            "service_id": service_id,
            "type": type,
            "amount": amount,
            "currency": currency,
            "models": json_encode(models),
            "effort": effort,
            "unit": unit,
            "referral_required": 1 if referral_required else 0,
            "status": status,
            "score": score,
            "url": url,
            "first_seen_at": _dt(first_seen_at),
            "conditions": json_encode(conditions),
        },
    )


def make_signal(
    *,
    service_id: Optional[int] = None,
    offer_id: Optional[int] = None,
    source: str = "test",
    source_url: Optional[str] = None,
    raw_text: Optional[str] = None,
    lang: Optional[str] = None,
    observed_at: Any = None,
) -> int:
    """Insert a ``signals`` row, return its id."""
    return _insert(
        "signals",
        {
            "service_id": service_id,
            "offer_id": offer_id,
            "source": source,
            "source_url": source_url,
            "raw_text": raw_text,
            "lang": lang,
            "observed_at": _dt(observed_at),
        },
    )

"""Canonical datetime ↔ storage-string helpers.

Storage format mirrors SQLAlchemy's default SQLite rendering
(``YYYY-MM-DD HH:MM:SS.ffffff``) so the raw-SQL path and the legacy ORM path
read/write interchangeable timestamps.

Two parse variants exist on purpose — do not collapse them:
  * :func:`parse_naive` → tz-naive datetime (storage rows, web serialization).
  * :func:`parse_utc`   → tz-aware UTC datetime (scoring/age math that needs it).

This module replaces the per-file ``_dt_str`` / ``_dt_parse`` / ``_iso`` copies
that previously lived in store.py, discover.py, enrich.py, watchdog.py,
scorer.py and web.py.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

# Accepted stored timestamp layouts, tried in order.
_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
)


def to_storage_str(d: Optional[dt.datetime]) -> Optional[str]:
    """Datetime → storage string (naive UTC, SQLAlchemy-compatible format)."""
    if d is None:
        return None
    if d.tzinfo is not None:
        d = d.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return d.strftime("%Y-%m-%d %H:%M:%S.%f")


def parse_naive(s) -> Optional[dt.datetime]:
    """Storage string → tz-naive datetime (or None).

    Accepts an already-parsed ``datetime`` (returned as-is). Falls back to
    ``fromisoformat`` and strips any tzinfo so callers get a naive value.
    """
    if not s:
        return None
    if isinstance(s, dt.datetime):
        return s
    for fmt in _FORMATS:
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        d = dt.datetime.fromisoformat(s)
        return d.replace(tzinfo=None) if d.tzinfo else d
    except ValueError:
        return None


def parse_utc(s) -> Optional[dt.datetime]:
    """Storage string → tz-aware UTC datetime (or None).

    Like :func:`parse_naive` but always returns a UTC-aware datetime, for age /
    lead-time math that compares against ``utcnow()``.
    """
    if not s:
        return None
    if isinstance(s, dt.datetime):
        return s if s.tzinfo else s.replace(tzinfo=dt.timezone.utc)
    for fmt in _FORMATS:
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    try:
        d = dt.datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def to_iso(s: Optional[str]) -> Optional[str]:
    """Storage datetime string → ISO-8601 string for JSON (or None)."""
    d = parse_naive(s)
    return d.isoformat() if d else None

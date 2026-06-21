"""Platform-agnostic Database protocol and factory.

Two implementations are selected at runtime via AIRADAR_PLATFORM:
  local       → SQLiteDatabase  (SQLAlchemy + SQLite/Postgres)
  cloudflare  → D1Database      (Cloudflare D1 REST API)

All business logic (store, scorer, watchdog, enrich) imports ONLY
from this module — never from sqlalchemy directly.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator, Protocol, Sequence, runtime_checkable


@runtime_checkable
class Database(Protocol):
    """Minimal SQL interface shared by all platform implementations."""

    def execute(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        """Run a SELECT, return rows as list of dicts."""
        ...

    def run(self, sql: str, params: Sequence[Any] = ()) -> None:
        """Run INSERT / UPDATE / DELETE."""
        ...

    def runmany(self, sql: str, params_list: Sequence[Sequence[Any]]) -> None:
        """Run INSERT / UPDATE for multiple rows."""
        ...

    def commit(self) -> None:
        """Commit the current transaction (no-op for auto-commit backends)."""
        ...

    def rollback(self) -> None:
        """Roll back the current transaction."""
        ...


# ─── DDL — shared SQL schema (SQLite-compatible, also works in D1) ───────────
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS services (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_domain  TEXT    NOT NULL UNIQUE,
    name              TEXT,
    type              TEXT    NOT NULL DEFAULT 'other',
    engine            TEXT,
    models            TEXT,           -- JSON array
    aliases           TEXT,           -- JSON array of all hosts seen
    status            TEXT    NOT NULL DEFAULT 'new',
    reliability       REAL    NOT NULL DEFAULT 0.0,
    domain_first_seen TEXT,           -- ISO datetime
    first_seen        TEXT    NOT NULL DEFAULT (datetime('now')),
    last_checked      TEXT
);

CREATE TABLE IF NOT EXISTS offers (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id        INTEGER NOT NULL REFERENCES services(id),
    type              TEXT    NOT NULL DEFAULT 'other',
    amount            REAL,
    currency          TEXT,
    models            TEXT,           -- JSON array
    claim_steps       TEXT,
    requirements      TEXT,
    referral_required INTEGER NOT NULL DEFAULT 0,
    effort            TEXT,           -- easy / medium / hard
    unit              TEXT,           -- usd / credits / days / months
    description       TEXT,           -- short blurb parsed from the service page
    url               TEXT,
    status            TEXT    NOT NULL DEFAULT 'new',
    score             REAL    NOT NULL DEFAULT 0.0,
    notified_at       TEXT,
    first_seen_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    last_verified_at  TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    offer_id       INTEGER REFERENCES offers(id),
    service_id     INTEGER REFERENCES services(id),
    source         TEXT    NOT NULL,
    source_url     TEXT,
    url            TEXT,
    raw_text       TEXT,
    lang           TEXT,
    classification TEXT,              -- JSON object
    confidence     REAL,
    observed_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, source_url)
);

CREATE TABLE IF NOT EXISTS sources (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT    NOT NULL UNIQUE,
    type     TEXT    NOT NULL,
    enabled  INTEGER NOT NULL DEFAULT 1,
    last_run TEXT,
    config   TEXT                     -- JSON object
);

CREATE TABLE IF NOT EXISTS lead_metrics (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    offer_id                 INTEGER NOT NULL UNIQUE REFERENCES offers(id),
    first_seen_by_us         TEXT,
    first_seen_in_aggregator TEXT,
    lead_hours               REAL
);
"""


# ─── Helpers shared across implementations ────────────────────────────────────

def json_encode(value: Any) -> str | None:
    """Encode a Python list/dict to JSON string for storage."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def json_decode(value: str | None) -> Any:
    """Decode a JSON string from storage back to Python object."""
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


# ─── Runtime factory — populated by runtime.py ───────────────────────────────

_db_factory = None  # Callable[[], contextmanager[Database]]


def _get_factory():
    global _db_factory
    if _db_factory is None:
        # Lazy import to avoid circular deps; runtime.py calls set_db_factory()
        from aiapiradar.runtime import setup
        setup()
    return _db_factory


def set_db_factory(factory) -> None:
    """Called by runtime.py once at startup."""
    global _db_factory
    _db_factory = factory


@contextmanager
def get_db() -> Iterator[Database]:
    """Get a database connection. Usage: `with get_db() as db: ...`"""
    factory = _get_factory()
    with factory() as db:
        yield db


def init_db() -> None:
    """Create all tables if they don't exist."""
    factory = _get_factory()
    with factory() as db:
        for stmt in SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                db.run(stmt)
        db.commit()

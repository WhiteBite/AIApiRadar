"""Database layer — platform-agnostic interface + implementations.

All access goes through the raw-SQL ``Database`` protocol (no ORM):

    from aiapiradar.db import get_db, init_db

    with get_db() as db:
        rows = db.execute("SELECT * FROM services WHERE status = ?", ["active"])
"""
from __future__ import annotations

from .base import (
    Database,
    get_db,
    json_decode,
    json_encode,
    set_db_factory,
)

__all__ = [
    "Database",
    "get_db",
    "init_db",
    "set_db_factory",
    "json_encode",
    "json_decode",
]


def init_db() -> None:
    """Create all tables via the Database protocol path (SCHEMA_SQL)."""
    from .base import init_db as _base_init_db

    _base_init_db()

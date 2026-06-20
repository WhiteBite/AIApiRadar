"""Runtime bootstrap: select and register the Database implementation.

Called lazily by aiapiradar.db.base.get_db() the first time a connection is
requested when no factory has been explicitly registered via set_db_factory().
"""
from __future__ import annotations


def setup() -> None:
    """Register the correct Database factory based on AIRADAR_PLATFORM."""
    from .config import get_settings
    from .db.base import set_db_factory

    settings = get_settings()
    if settings.is_cloudflare:
        raise NotImplementedError(
            "Cloudflare D1 implementation is not yet available. "
            "Set AIRADAR_PLATFORM=local to use the SQLite backend."
        )
    from .db.sqlite import sqlite_db_factory

    set_db_factory(sqlite_db_factory)

"""Database layer — platform-agnostic interface + implementations.

Primary usage (new code):

    from aiapiradar.db import get_db, init_db

    with get_db() as db:
        rows = db.execute("SELECT * FROM services WHERE status = ?", ["active"])

Backward-compat shim (legacy tests / old callers):

    import aiapiradar.db as db

    db._engine = None          # reset between tests
    db._SessionFactory = None
    db.init_db()               # create tables
    with db.session_scope() as s:
        s.query(...)
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

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
    "session_scope",
]


# ─── Backward-compat shim: SQLAlchemy ORM session ────────────────────────────
# These module-level names are patched by legacy tests:
#   import aiapiradar.db as db; db._engine = None; db._SessionFactory = None

_engine = None
_SessionFactory = None


def _get_engine():
    global _engine
    if _engine is None:
        from sqlalchemy import create_engine

        from ..config import get_settings

        url = get_settings().db_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, future=True, connect_args=connect_args)
    return _engine


def _get_session_factory():
    global _SessionFactory
    if _SessionFactory is None:
        from sqlalchemy.orm import Session, sessionmaker

        _SessionFactory = sessionmaker(
            bind=_get_engine(), class_=Session, expire_on_commit=False
        )
    return _SessionFactory


def init_db() -> None:
    """Create all tables.

    Uses the new Database protocol path (SCHEMA_SQL) so both the sqlite3 path
    and the SQLAlchemy ORM path see the same schema.
    """
    from .base import init_db as _base_init_db

    _base_init_db()


@contextmanager
def session_scope() -> Iterator:
    """Transactional SQLAlchemy session (backward compat for legacy code / tests)."""
    factory = _get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

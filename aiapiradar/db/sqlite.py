"""SQLiteDatabase — local/VPS implementation using Python's stdlib sqlite3.

Uses sqlite3 directly (no SQLAlchemy ORM), keeping parity with the D1
implementation.  The context-manager factory opens a connection, yields the
database object, commits on success and rolls back on error.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator, Sequence


class SQLiteDatabase:
    """Thin wrapper around a sqlite3.Connection that satisfies the Database Protocol."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def execute(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        """Run a SELECT (or INSERT … RETURNING); return rows as list of dicts."""
        cur = self._conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def run(self, sql: str, params: Sequence[Any] = ()) -> None:
        """Run INSERT / UPDATE / DELETE."""
        self._conn.execute(sql, params)

    def runmany(self, sql: str, params_list: Sequence[Sequence[Any]]) -> None:
        """Run a statement for each item in params_list."""
        self._conn.executemany(sql, params_list)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()


@contextmanager
def sqlite_db_factory() -> Iterator[SQLiteDatabase]:
    """Open a connection to the configured SQLite file, yield a SQLiteDatabase.

    Commits on clean exit; rolls back and re-raises on any exception.
    """
    from ..config import get_settings

    settings = get_settings()
    # Strip the SQLAlchemy URL prefix to get a plain filesystem path.
    db_path = settings.db_url.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    db = SQLiteDatabase(conn)
    try:
        yield db
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

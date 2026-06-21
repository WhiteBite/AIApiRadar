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
        from .db.d1 import d1_db_factory

        set_db_factory(d1_db_factory)
        return
    from .db.sqlite import sqlite_db_factory

    set_db_factory(sqlite_db_factory)


def get_runner():
    """Select the execution runner for the current platform.

    This is the scheduler/runner counterpart to `setup()` (which selects the
    DB backend). Rather than dead-ending on the cloudflare path, it routes to
    the one-shot batch runner — the serverless/CI execution model — while the
    long-lived APScheduler process runner remains the default on local/VDS.

    Returns a zero-arg callable that runs the selected runner to completion
    (see aiapiradar.sched.get_runner for the process/batch split).
    """
    from .sched import get_runner as _select_runner

    return _select_runner()

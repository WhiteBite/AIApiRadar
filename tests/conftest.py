"""Shared pytest fixtures + factory re-exports for the raw-SQL test path.

``db_env`` replicates the proven reset used by test_cross_source.py: point the
app at a throwaway SQLite file via env, clear the cached settings, reset the
legacy ORM engine/session singletons (still present until the ORM is removed),
and create the schema through the Database-protocol ``init_db()``.

Factories are re-exported here so tests can ``from tests.factories import ...``
(package-qualified) or rely on the fixture; see tests/factories.py.
"""
from __future__ import annotations

import pytest

from tests.factories import make_offer, make_service, make_signal  # noqa: F401


@pytest.fixture()
def db_env(tmp_path, monkeypatch):
    """Function-scoped DB reset: fresh SQLite file + schema, via the prod path."""
    monkeypatch.setenv("AIRADAR_DB_URL", f"sqlite:///{tmp_path / 'test.db'}")

    import aiapiradar.config as config
    import aiapiradar.db as db

    config.get_settings.cache_clear()
    db._engine = None
    db._SessionFactory = None
    db.init_db()
    try:
        yield
    finally:
        config.get_settings.cache_clear()

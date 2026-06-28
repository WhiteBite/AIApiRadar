"""Phase 0 smoke tests: core abstractions + DB schema wire together."""
from __future__ import annotations

import asyncio

from aiapiradar.core import Collector, Signal
from aiapiradar.collectors import register, get_registry


def test_signal_dedup_key():
    s = Signal(source="certstream", url="https://foo.bar", source_url="https://foo.bar/cert")
    assert s.dedup_key() == "certstream|https://foo.bar/cert"
    s2 = Signal(source="x", raw_text="hello world " * 20)
    assert s2.dedup_key().startswith("x|hello world")


def test_collector_registry_and_collect():
    @register
    class DummyCollector(Collector):
        name = "dummy_test"
        kind = "test"
        interval = 60

        async def collect(self):
            return [Signal(source=self.name, raw_text="free $200 credits register")]

    assert "dummy_test" in get_registry()
    signals = asyncio.run(DummyCollector().collect())
    assert len(signals) == 1
    assert signals[0].source == "dummy_test"


def test_db_init_and_roundtrip(db_env):
    from aiapiradar.db import get_db
    from tests.factories import make_service

    make_service("freemodel.dev", name="FreeModel", type="relay")

    with get_db() as db:
        rows = db.execute(
            "SELECT name, status FROM services WHERE canonical_domain = ?",
            ["freemodel.dev"],
        )
    assert len(rows) == 1
    assert rows[0]["name"] == "FreeModel"
    assert rows[0]["status"] == "new"

"""Phase 2 tests: the three collectors (pure parse paths, no network) and
their integration with the pipeline."""
from __future__ import annotations

import asyncio

from aiapiradar.collectors import get_registry, load_builtin
from aiapiradar.collectors.certstream import CertStreamCollector, domain_matches
from aiapiradar.collectors.forum_rss import parse_feed
from aiapiradar.collectors.directories import parse_listing
from aiapiradar.core.signal import Signal


# --- registry --------------------------------------------------------------
def test_builtin_collectors_register():
    load_builtin()
    names = set(get_registry())
    assert {"certstream", "forum_rss", "directories"} <= names


# --- certstream ------------------------------------------------------------
def test_domain_matches():
    assert domain_matches("swiftrouter.com")
    assert domain_matches("api-cc.freemodel.dev")
    assert domain_matches("*.newapi.example.com")
    assert not domain_matches("example.com")
    assert not domain_matches("googleapis.com")


def test_certstream_drains_buffer(monkeypatch):
    monkeypatch.setattr(CertStreamCollector, "ensure_started", classmethod(lambda cls: None))
    CertStreamCollector._buffer.clear()
    CertStreamCollector._buffer.extend(["swiftrouter.com", "freemodel.dev"])
    signals = list(asyncio.run(CertStreamCollector().collect()))
    assert len(signals) == 2
    assert all(s.meta.get("service_candidate") for s in signals)
    assert signals[0].url.startswith("https://")


# --- forum rss -------------------------------------------------------------
RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>新中转站上线 注册送 $20 额度</title>
    <link>https://nodeseek.com/post/12345</link>
    <description>支持 claude gpt gemini, 访问 https://newrelay.example 注册即送</description>
  </item>
</channel></rss>"""


def test_parse_feed():
    sigs = parse_feed(RSS, "nodeseek")
    assert len(sigs) == 1
    assert sigs[0].source == "nodeseek"
    assert sigs[0].source_url == "https://nodeseek.com/post/12345"
    assert "注册送" in sigs[0].raw_text


# --- directories -----------------------------------------------------------
HTML = """
<html><body>
  <a href="/internal">internal link</a>
  <a href="https://twitter.com/foo">social</a>
  <a href="https://coolnewtool.ai" title="Free trial AI agent">CoolTool — $50 free credits</a>
</body></html>
"""


def test_parse_listing_filters_self_and_social():
    sigs = parse_listing(HTML, "https://theresanaiforthat.com/just-launched/", "theresanaiforthat")
    hosts = {s.url for s in sigs}
    assert "https://coolnewtool.ai" in hosts
    assert not any("twitter.com" in (s.url or "") for s in sigs)
    assert all(not (s.url or "").startswith("https://theresanaiforthat.com") for s in sigs)


# --- integration: collectors -> pipeline -> DB ----------------------------
def test_collectors_into_pipeline(db_env):
    from aiapiradar.db import get_db
    from aiapiradar.pipeline.pipeline import Pipeline
    from aiapiradar.pipeline.classify import HeuristicClassifier

    pipe = Pipeline(classifier=HeuristicClassifier())

    forum_sigs = parse_feed(RSS, "nodeseek")
    dir_sigs = parse_listing(HTML, "https://theresanaiforthat.com/just-launched/", "theresanaiforthat")
    candidate = Signal(
        source="certstream", raw_text="swiftrouter.com", url="https://swiftrouter.com",
        source_url="certstream://swiftrouter.com",
        meta={"service_candidate": True, "force_classify": True},
    )
    stats = pipe.process_signals([*forum_sigs, *dir_sigs, candidate])

    assert stats.get("candidates", 0) == 1  # certstream seeded a service, no offer
    with get_db() as db:
        # coolnewtool ($50 offer) + swiftrouter (candidate) -> >= 2 services
        assert db.execute("SELECT COUNT(*) AS n FROM services")[0]["n"] >= 2
        assert db.execute("SELECT COUNT(*) AS n FROM offers")[0]["n"] >= 1
        assert db.execute(
            "SELECT COUNT(*) AS n FROM services WHERE canonical_domain = ?",
            ["swiftrouter.com"],
        )[0]["n"] == 1

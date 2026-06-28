"""Epic A1 tests: domain blocklist anti-noise.

Covers the pure is_blocked_domain() helper (incl. subdomain resolution via
registrable_domain) and the pipeline-level guarantee that a blocked-domain
signal never creates a Service/offer.
"""
from __future__ import annotations

import pytest

from aiapiradar.core.signal import Signal
from aiapiradar.pipeline import normalize
from aiapiradar.pipeline.classify import HeuristicClassifier


# --- is_blocked_domain -----------------------------------------------------
@pytest.mark.parametrize(
    "domain",
    ["reddit.com", "www.reddit.com", "old.reddit.com", "https://reddit.com/r/x/1"],
)
def test_is_blocked_domain_true_for_reddit_variants(domain):
    assert normalize.is_blocked_domain(domain) is True


def test_is_blocked_domain_false_for_real_service():
    assert normalize.is_blocked_domain("verdent.ai") is False
    assert normalize.is_blocked_domain("https://verdent.ai/pricing") is False


def test_is_blocked_domain_none_safe():
    assert normalize.is_blocked_domain(None) is False


# --- pipeline does NOT create a service for a blocked domain ---------------
def test_pipeline_skips_blocked_domain_signal(db_env):
    from aiapiradar.pipeline.pipeline import Pipeline
    from aiapiradar.db import get_db

    pipe = Pipeline(classifier=HeuristicClassifier())
    signals = [
        # Looks like an offer textually, but the only domain is the platform.
        Signal(
            source="reddit",
            raw_text="reddit.com gives $200 free credits, sign up now https://reddit.com",
            url="https://www.reddit.com/r/test/1",
            source_url="https://reddit.com/r/test/1",
        ),
    ]
    stats = pipe.process_signals(signals)

    assert stats.get("blocked", 0) == 1
    with get_db() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM services")[0]["n"] == 0
        assert db.execute("SELECT COUNT(*) AS n FROM offers")[0]["n"] == 0


def test_pipeline_keeps_real_domain_signal(db_env):
    """Control: a non-blocked domain with the same text still creates a service."""
    from aiapiradar.pipeline.pipeline import Pipeline
    from aiapiradar.db import get_db

    pipe = Pipeline(classifier=HeuristicClassifier())
    signals = [
        Signal(
            source="reddit",
            raw_text="verdent.ai gives $200 free credits, sign up now https://verdent.ai",
            url="https://verdent.ai",
            source_url="https://reddit.com/r/test/2",
        ),
    ]
    pipe.process_signals(signals)
    with get_db() as db:
        assert db.execute(
            "SELECT COUNT(*) AS n FROM services WHERE canonical_domain = ?",
            ["verdent.ai"],
        )[0]["n"] == 1

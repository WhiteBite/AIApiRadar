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


# --- retail marketplaces are blocked (never AI services) -------------------
@pytest.mark.parametrize(
    "domain",
    ["ebay.com", "www.ebay.com", "aliexpress.com", "taobao.com", "walmart.com",
     "etsy.com", "wildberries.ru"],
)
def test_retail_marketplaces_blocked(domain):
    assert normalize.is_blocked_domain(domain) is True


def test_amazon_not_blocked_aws():
    # amazon.com stays allowed on purpose — it's AWS, a legit seeded service.
    assert normalize.is_blocked_domain("amazon.com") is False


# --- is_plausible_offer: implausible amounts are a misparse ----------------
def _clf(**kw):
    from aiapiradar.pipeline.classify import Classification
    base = dict(is_offer=True, offer_type="saas_trial", amount=2500.0,
                currency="USD", unit="usd", confidence=0.8)
    base.update(kw)
    return Classification(**base)


def test_is_plausible_offer_rejects_big_usd_trial():
    from aiapiradar.pipeline.classify import is_plausible_offer
    assert is_plausible_offer(_clf(offer_type="saas_trial", amount=2500.0)) is False
    assert is_plausible_offer(_clf(offer_type="relay", amount=5000.0)) is False


def test_is_plausible_offer_accepts_normal_amounts():
    from aiapiradar.pipeline.classify import is_plausible_offer
    assert is_plausible_offer(_clf(amount=200.0)) is True       # typical trial
    assert is_plausible_offer(_clf(amount=None)) is True        # no amount
    # grants legitimately run large (cloud startup credits) — never rejected
    assert is_plausible_offer(_clf(offer_type="grant", amount=100000.0)) is True
    # credits unit (not USD) is never rejected by the USD ceiling
    assert is_plausible_offer(_clf(amount=50000.0, currency=None, unit="credits")) is True


def test_pipeline_rejects_implausible_amount(db_env):
    """The ebay/$2500 scenario: a hardware price misread as a trial → no offer."""
    from aiapiradar.pipeline.pipeline import Pipeline
    from aiapiradar.db import get_db

    pipe = Pipeline(classifier=HeuristicClassifier())
    signals = [
        Signal(
            source="reddit",
            raw_text="running glm on budget hardware $2500 free trial included https://hardware-shop.dev",
            url="https://hardware-shop.dev",
            source_url="https://reddit.com/r/localllama/abc",
        ),
    ]
    stats = pipe.process_signals(signals)

    assert stats.get("implausible", 0) == 1
    with get_db() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM offers")[0]["n"] == 0

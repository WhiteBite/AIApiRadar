"""Phase 6 tests: remaining collectors (pure parse) + model_release pipeline path."""
from __future__ import annotations

from aiapiradar.collectors import get_registry, load_builtin
from aiapiradar.collectors.github import parse_search
from aiapiradar.collectors.huggingface import parse_models
from aiapiradar.collectors.producthunt import parse_feed as ph_parse
from aiapiradar.collectors.searchdorks import parse_results
from aiapiradar.collectors.coupon import parse_coupon


def test_all_collectors_register():
    load_builtin()
    names = set(get_registry())
    assert {"certstream", "forum_rss", "directories", "github", "huggingface",
            "producthunt", "searchdorks", "coupon"} <= names


def test_github_parse_search():
    data = {"items": [
        {"full_name": "foo/free-ai", "description": "Free $200 credits claude gpt",
         "html_url": "https://github.com/foo/free-ai", "homepage": "https://freeai.example",
         "stargazers_count": 12},
        {"name": "empty", "description": "", "html_url": "https://github.com/x/empty"},
    ]}
    sigs = parse_search(data)
    assert len(sigs) == 1
    assert sigs[0].url == "https://freeai.example"
    assert "free" in sigs[0].raw_text.lower()


def test_huggingface_parse_models_filters_orgs():
    data = [
        {"id": "zai-org/GLM-5.2"},
        {"id": "thudm/chatglm4"},
        {"id": "randomuser/mymodel"},   # not a key org -> skipped
        {"id": "no-slash-id"},          # malformed -> skipped
    ]
    sigs = parse_models(data)
    ids = {s.meta["model_id"] for s in sigs}
    assert ids == {"zai-org/GLM-5.2", "thudm/chatglm4"}
    assert all(s.meta.get("model_release") for s in sigs)


PH_RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>CoolAI — agent platform</title><link>https://producthunt.com/posts/coolai</link>
<description>Launch with free trial credits</description></item>
</channel></rss>"""


def test_producthunt_parse():
    sigs = ph_parse(PH_RSS)
    assert len(sigs) == 1 and sigs[0].source == "producthunt"
    assert "free trial" in sigs[0].raw_text.lower()


def test_searchdorks_parse():
    data = {"items": [
        {"title": "Get $100 free credits", "snippet": "register now", "link": "https://x.ai/promo"},
        {"title": "no link"},
    ]}
    sigs = parse_results(data)
    assert len(sigs) == 1 and sigs[0].url == "https://x.ai/promo"


COUPON_HTML = """
<html><head><title>Gumloop Promo Codes & Deals</title>
<meta name="description" content="Flat 20% OFF on annual subscription"/></head>
<body><p>Use this Gumloop coupon for 20% off your first purchase.</p></body></html>
"""


def test_coupon_parse():
    sigs = parse_coupon(COUPON_HTML, "gumloop.com", "grabon", "https://grabon.in/gumloop-coupons/")
    assert len(sigs) == 1
    assert sigs[0].url == "https://gumloop.com"
    assert "20% off" in sigs[0].raw_text.lower() or "20% OFF" in sigs[0].raw_text


def test_model_release_pipeline(db_env):
    from aiapiradar.pipeline.pipeline import Pipeline
    from aiapiradar.pipeline.classify import HeuristicClassifier
    from aiapiradar.db import get_db

    hf_sigs = parse_models([{"id": "zai-org/GLM-5.2"}])
    pipe = Pipeline(classifier=HeuristicClassifier())
    stats = pipe.process_signals(hf_sigs)
    assert stats.get("model_releases", 0) == 1

    # re-run: same model url -> no duplicate offer
    pipe.process_signals(parse_models([{"id": "zai-org/GLM-5.2"}]))
    with get_db() as db:
        svc = db.execute(
            "SELECT id, type FROM services WHERE canonical_domain = ?",
            ["hf/zai-org"],
        )
        assert len(svc) == 1
        assert svc[0]["type"] == "model_release"
        n_offers = db.execute(
            "SELECT COUNT(*) AS n FROM offers WHERE service_id = ?",
            [svc[0]["id"]],
        )[0]["n"]
        assert n_offers == 1

"""Phase 1 tests: normalize, prefilter, heuristic classify, and the full
pipeline persisting into a temp DB (incl. a run over the real chat export)."""
from __future__ import annotations

import json
import os

import pytest

from aiapiradar.core.signal import Signal
from aiapiradar.pipeline import normalize, prefilter
from aiapiradar.pipeline.classify import HeuristicClassifier


# --- normalize -------------------------------------------------------------
def test_detect_lang():
    assert normalize.detect_lang("free credits register") == "en"
    assert normalize.detect_lang("дает бесплатные кредиты") == "ru"
    assert normalize.detect_lang("注册送 额度 免费") == "zh"


def test_canonical_domain():
    assert normalize.canonical_domain("https://www.Nanonets.com/pricing") == "nanonets.com"
    assert normalize.canonical_domain("freemodel.dev") == "freemodel.dev"
    assert normalize.canonical_domain(None) is None


def test_extract_service_domains_skips_infra():
    s = Signal(
        source="x",
        raw_text="check https://freemodel.dev and https://t.me/foo and https://github.com/a/b",
    )
    domains = normalize.extract_service_domains(s)
    assert "freemodel.dev" in domains
    assert "t.me" not in domains and "github.com" not in domains


# --- prefilter -------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("Get $200 free credits, sign up", True),
        ("注册送 额度 公益站", True),
        ("дают триальный баланс при регистрации", True),
        ("just a normal sentence about cats", False),
    ],
)
def test_prefilter(text, expected):
    matched, _ = prefilter.match(text)
    assert matched is expected


# --- heuristic classifier --------------------------------------------------
def test_heuristic_classifier_extracts_amount_and_models():
    clf = HeuristicClassifier()
    res = clf.classify(
        "Nanonets gives $200 free credits. Models: Opus, GPT, Gemini. Register now.",
        url="https://nanonets.com/",
        lang="en",
        domains=["nanonets.com"],
    )
    assert res.is_offer
    assert res.amount == 200.0
    assert "gpt" in res.models and "gemini" in res.models
    assert res.confidence > 0.6


# --- full pipeline into temp DB -------------------------------------------
def _reset_db(tmp_path, monkeypatch):
    db_file = tmp_path / "p1.db"
    monkeypatch.setenv("AIRADAR_DB_URL", f"sqlite:///{db_file}")
    import aiapiradar.config as config
    import aiapiradar.db as db
    config.get_settings.cache_clear()
    db._engine = None
    db._SessionFactory = None
    db.init_db()
    return db


def test_pipeline_persists_and_dedups(tmp_path, monkeypatch):
    db = _reset_db(tmp_path, monkeypatch)
    from aiapiradar.pipeline.pipeline import Pipeline
    from aiapiradar.models import Service, Offer, Signal as SigRow

    pipe = Pipeline(classifier=HeuristicClassifier())
    signals = [
        Signal(source="nodeseek", raw_text="freemodel.dev $300 free credits register https://freemodel.dev",
               source_url="https://nodeseek.com/post/1"),
        # duplicate source_url -> must be skipped
        Signal(source="nodeseek", raw_text="freemodel.dev $300 free credits register https://freemodel.dev",
               source_url="https://nodeseek.com/post/1"),
        # same service, second mention from another source -> updates offer, new signal
        Signal(source="reddit", raw_text="freemodel.dev gives $300 credits, claude gpt",
               source_url="https://reddit.com/r/x/2", url="https://freemodel.dev"),
        # noise -> prefiltered out
        Signal(source="reddit", raw_text="my cat is cute", source_url="https://reddit.com/r/x/3"),
    ]
    stats = pipe.process_signals(signals)

    assert stats["dup"] == 1
    assert stats["prefiltered_out"] == 1
    with db.session_scope() as s:
        assert s.query(Service).count() == 1
        assert s.query(Offer).count() == 1          # deduped to a single offer
        assert s.query(SigRow).count() == 2          # two unique stored signals


def test_pipeline_over_real_export(tmp_path, monkeypatch):
    """If the parsed real chat export exists, the pipeline should detect
    known offers (nanonets, evomap, freemodel) — real-data validation."""
    fixture = os.path.join(os.getcwd(), "parsed_messages.jsonl")
    if not os.path.exists(fixture):
        pytest.skip("parsed_messages.jsonl not present")

    db = _reset_db(tmp_path, monkeypatch)
    from aiapiradar.pipeline.pipeline import Pipeline
    from aiapiradar.models import Service

    pipe = Pipeline(classifier=HeuristicClassifier())
    raw = []
    with open(fixture, encoding="utf-8") as f:
        for line in f:
            m = json.loads(line)
            links = m.get("links") or []
            raw.append(Signal(
                source="export",
                raw_text=m.get("text") or "",
                url=(links[0] if links else None),
                source_url=f"export#{len(raw)}",
            ))
    stats = pipe.process_signals(raw)
    assert stats["seen"] > 100
    with db.session_scope() as s:
        domains = {d for (d,) in s.query(Service.canonical_domain).all()}
    # at least some known services must surface from real data
    assert domains & {"nanonets.com", "evomap.ai", "freemodel.dev", "swiftrouter.com"}

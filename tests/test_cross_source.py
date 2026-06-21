"""Tests for cross-source confirmation score boost in _rescore_all_db."""
from __future__ import annotations

import datetime as dt

from aiapiradar.db import get_db
from aiapiradar.models import utcnow
from aiapiradar.scorer import _rescore_all_db


def _reset_db(tmp_path, monkeypatch, name="cs.db"):
    monkeypatch.setenv("AIRADAR_DB_URL", f"sqlite:///{tmp_path / name}")
    import aiapiradar.config as config
    import aiapiradar.db as db

    config.get_settings.cache_clear()
    db._engine = None
    db._SessionFactory = None
    db.init_db()


def test_cross_source_boost_increases_score(tmp_path, monkeypatch):
    """An offer whose service has signals from 3 distinct sources must score
    higher than an otherwise identical offer with only 1 signal source.

    With the boost formula:
        boost = 1.0 + 0.15 * min(max(0, source_count - 1), 3)
    - single source (count=1): boost = 1.0
    - three sources (count=3): boost = 1.30
    So multi_score / single_score should be ~1.30.
    """
    _reset_db(tmp_path, monkeypatch)

    # Use a very recent first_seen_at so recency_decay ≈ 1.0 and scores stay
    # well above the rounding-to-zero threshold.
    now = utcnow()
    fresh_str = (now - dt.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S.%f")

    with get_db() as db:
        # --- single-source service & offer ---
        db.run(
            "INSERT INTO services (canonical_domain, name, type, reliability) "
            "VALUES (?, ?, ?, ?)",
            ["single.example.com", "SingleSource", "relay", 0.5],
        )
        single_id = db.execute(
            "SELECT id FROM services WHERE canonical_domain = ?",
            ["single.example.com"],
        )[0]["id"]

        db.run(
            "INSERT INTO offers "
            "(service_id, type, amount, referral_required, first_seen_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [single_id, "saas_trial", 100.0, 0, fresh_str],
        )
        single_offer_id = db.execute(
            "SELECT id FROM offers WHERE service_id = ?", [single_id]
        )[0]["id"]

        # 1 signal
        db.run(
            "INSERT INTO signals (service_id, source, source_url) VALUES (?, ?, ?)",
            [single_id, "hackernews", "https://hn.example.com/1"],
        )

        # --- multi-source service & offer (identical except signals) ---
        db.run(
            "INSERT INTO services (canonical_domain, name, type, reliability) "
            "VALUES (?, ?, ?, ?)",
            ["multi.example.com", "MultiSource", "relay", 0.5],
        )
        multi_id = db.execute(
            "SELECT id FROM services WHERE canonical_domain = ?",
            ["multi.example.com"],
        )[0]["id"]

        db.run(
            "INSERT INTO offers "
            "(service_id, type, amount, referral_required, first_seen_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [multi_id, "saas_trial", 100.0, 0, fresh_str],
        )
        multi_offer_id = db.execute(
            "SELECT id FROM offers WHERE service_id = ?", [multi_id]
        )[0]["id"]

        # 3 signals from 3 different sources
        for src, url in [
            ("hackernews", "https://hn.example.com/2"),
            ("forum_rss", "https://forum.example.com/1"),
            ("github_lists", "https://github.example.com/1"),
        ]:
            db.run(
                "INSERT INTO signals (service_id, source, source_url) "
                "VALUES (?, ?, ?)",
                [multi_id, src, url],
            )

        count = _rescore_all_db(db)
        assert count == 2

        single_score = db.execute(
            "SELECT score FROM offers WHERE id = ?", [single_offer_id]
        )[0]["score"]
        multi_score = db.execute(
            "SELECT score FROM offers WHERE id = ?", [multi_offer_id]
        )[0]["score"]

    assert single_score > 0.0, "single-source score should be non-zero"
    assert multi_score > single_score, (
        f"multi-source score ({multi_score}) should exceed "
        f"single-source score ({single_score})"
    )
    # boost(3 sources) = 1.30, boost(1 source) = 1.0 → ratio ≈ 1.30
    ratio = multi_score / single_score
    assert abs(ratio - 1.30) < 0.02, (
        f"Expected ~1.30× boost, got {ratio:.4f} "
        f"(single={single_score}, multi={multi_score})"
    )

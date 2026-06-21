"""Tests for page-content extraction added to enrich (description/models/amount)."""
from __future__ import annotations

from aiapiradar.enrich import detect_models, detect_amount, _make_description


def test_detect_models():
    txt = "Access Claude Opus, GPT-4, and Gemini via one API."
    models = detect_models(txt)
    assert "claude" in models and "opus" in models
    assert "gpt" in models and "gemini" in models


def test_detect_amount_requires_credit_context():
    # A bare large number (revenue/stat) must NOT be taken as the offer amount.
    assert detect_amount("We saved customers $80,170 last year.") is None
    # Amount next to a free-credit trigger is accepted.
    assert detect_amount("Get $200 in free credits when you sign up.") == 200.0
    assert detect_amount("注册送 100 额度") == 100.0


def test_detect_amount_capped():
    # Above the sane free-credit ceiling -> rejected even with trigger.
    assert detect_amount("free credits worth $999999") is None


def test_make_description_from_meta():
    html = (
        '<html><head><meta name="description" '
        'content="FooAI is an agentic coding suite with parallel agents.">'
        "</head><body>x</body></html>"
    )
    desc = _make_description(html)
    assert desc and "agentic coding suite" in desc

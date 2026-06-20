"""Cheap rule-based pre-filter.

Drops obvious noise BEFORE the expensive LLM classification step. Multilingual:
Russian / English / Chinese, matching the real ecosystem we analysed.
"""
from __future__ import annotations

import re

# Lowercased substrings. Chinese kept as-is (case-insensitive lower is a no-op).
KEYWORDS = {
    "ru": [
        "триал", "кредит", "бесплатн", "api ключ", "апи ключ", "регистрац",
        "раздач", "раздают", "баланс", "халяв", "промокод", "бонус",
    ],
    "en": [
        "free credit", "free tier", "free trial", "api trial", "free api",
        "credits", "sign up", "signup", "register", "no card", "no credit card",
        "$", "promo", "redeem", "referral", "invite",
    ],
    "zh": [
        "注册送", "公益站", "中转站", "免费", "白嫖", "送额度", "送余额",
        "送刀", "额度", "免费额度", "注册即送",
    ],
}

_ALL = [k for ks in KEYWORDS.values() for k in ks]
# Money patterns that strongly imply an offer.
_MONEY_RE = re.compile(r"\$\s?\d+|\d+\s*(?:刀|美元|баллов|credits?)", re.IGNORECASE)


def match(text: str) -> tuple[bool, list[str]]:
    """Return (is_candidate, matched_keywords)."""
    if not text:
        return False, []
    low = text.lower()
    hits = [k for k in _ALL if k in low]
    if _MONEY_RE.search(text) and "$" not in hits:
        hits.append("$money")
    return (len(hits) > 0), hits

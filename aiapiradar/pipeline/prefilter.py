"""Cheap rule-based pre-filter.

Drops obvious noise BEFORE the expensive classification step. Multilingual:
Russian / English / Chinese, matching the real ecosystem we analysed.

Scoring logic (prevents Show HN / generic product pages from being ingested):
- Any ZH strong-offer keyword → immediate pass (chinese relay scene is high signal)
- RU keyword → pass (Russian ecosystem posts are consistently on-topic)
- EN: requires EITHER a "strong" keyword (explicit free-credit phrase) OR ≥2 EN hits
  This stops single-word matches like "register" or "$25/mo" from flooding the pipeline
  with unrelated product launches.
- Direct money pattern in text always adds a "$money" hit (contributes to EN ≥2 rule)
"""
from __future__ import annotations

import re

# ─── Chinese (strong signal — any single hit passes) ─────────────────────────
ZH_STRONG = [
    "注册送", "公益站", "中转站", "免费api", "白嫖", "送额度", "送余额",
    "送刀", "免费额度", "注册即送", "新用户送",
]
# Also worth checking (contributes to count)
ZH_WEAK = ["免费", "额度", "中转"]

# ─── Russian (any single hit passes) ─────────────────────────────────────────
RU_KEYWORDS = [
    "триал", "кредит", "бесплатн", "api ключ", "апи ключ", "регистрац",
    "раздач", "раздают", "баланс", "халяв", "промокод", "бонус",
]

# ─── English ──────────────────────────────────────────────────────────────────
# Strong: a single match is enough to pass.
EN_STRONG = [
    "free credit", "free credits", "free trial", "free api", "free tier",
    "api trial", "no credit card", "no card required", "sign up free",
    "register for free", "free access", "free tokens", "free quota",
    "get free", "claim free", "free plan includes",
    # Promo/coupon patterns: explicit enough to pass on their own
    "promo code", "coupon code", "discount code", "use code",
    # Free PRO/Pro plan announcements ("get PRO free", "free PRO plan")
    "free pro", "pro for free", "pro plan free",
    # Common startup launch phrasings that imply free access
    "get it free", "access for free", "free with",
]
# Weak: need ≥2 weak hits (or 1 strong) to pass — prevents "register" alone
# from pulling in every SaaS launch.
EN_WEAK = [
    "credits", "sign up", "signup", "register", "redeem",
    "promo", "referral", "invite", "api key", "trial", "$",
]

# Money pattern adds one "EN weak" hit
_MONEY_RE = re.compile(
    r"\$\s?\d+|¥\d+|\d+\s*(?:刀|美元|баллов|credits?|tokens?)\b",
    re.IGNORECASE,
)

_ALL_KEYWORDS = ZH_STRONG + ZH_WEAK + RU_KEYWORDS + EN_STRONG + EN_WEAK


def match(text: str) -> tuple[bool, list[str]]:
    """Return (is_candidate, matched_keywords).

    True when the signal is plausibly about obtaining free AI API access.
    """
    if not text:
        return False, []
    low = text.lower()

    # Chinese strong → pass immediately.
    for kw in ZH_STRONG:
        if kw in low:
            return True, [kw]

    # Chinese weak → accumulate
    zh_hits = [k for k in ZH_WEAK if k in low]
    if len(zh_hits) >= 2:
        return True, zh_hits

    # Russian → any single hit passes.
    ru_hits = [k for k in RU_KEYWORDS if k in low]
    if ru_hits:
        return True, ru_hits

    # English: strong = immediate pass.
    en_strong_hits = [k for k in EN_STRONG if k in low]
    if en_strong_hits:
        return True, en_strong_hits

    # English: weak ≥ 2 (including money pattern).
    en_weak_hits = [k for k in EN_WEAK if k in low]
    if _MONEY_RE.search(text):
        en_weak_hits.append("$money")
    if len(en_weak_hits) >= 2:
        return True, en_weak_hits

    return False, []

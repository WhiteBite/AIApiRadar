"""Model-name detection, free-credit amount parsing and engine fingerprinting.

Pure text analysers run over the visible text / title pulled from a probed
service. No network here — callers feed in already-fetched text.
"""
from __future__ import annotations

import re
from typing import Optional

from .text import _title

# Model keywords → canonical label (for facts parsed off the service page).
#
# Split into two groups to avoid false positives:
#
#   _SUBSTR_TOKENS  — longer, distinctive strings safe for plain substring
#                     matching (e.g. "claude", "gemini", "deepseek").
#
#   _EXACT_TOKENS   — short / ambiguous tokens that must NOT match inside
#                     unrelated words.  For these we require that the token
#                     is NOT immediately preceded or followed by a letter,
#                     e.g.  "gpt"  matches "gpt-4" and "use gpt today" but
#                     NOT "egypt" or "agpt".  A pre-compiled regex is built
#                     for each token in _EXACT_TOKENS below.
_SUBSTR_TOKENS: dict[str, str] = {
    "claude": "claude", "opus": "opus", "sonnet": "sonnet", "haiku": "haiku",
    "gpt-5": "gpt", "gpt-4": "gpt", "gpt4": "gpt", "openai": "gpt",
    "gemini": "gemini", "deepseek": "deepseek",
    "grok": "grok", "llama": "llama", "qwen": "qwen",
    "mistral": "mistral", "kimi": "kimi",
}

# Short tokens that require a non-letter boundary on both sides.
_EXACT_TOKENS: dict[str, str] = {
    "gpt": "gpt",   # would match "egypt", "agpt" etc. without boundary check
    "o1":  "gpt",   # very short; matches "o1" in scientific/version strings
    "o3":  "gpt",   # same
    "glm": "glm",   # would match inside longer words
}

# Pre-compile one regex per exact token: (?<![a-z])TOKEN(?![a-z])
# Applied to the already-lowercased text blob.
_EXACT_RES: dict[str, tuple[re.Pattern, str]] = {
    token: (re.compile(r"(?<![a-z])" + re.escape(token) + r"(?![a-z])"), label)
    for token, label in _EXACT_TOKENS.items()
}
_AMOUNT_USD_RE = re.compile(r"\$\s?(\d{1,3}(?:[,\s]?\d{3})*(?:\.\d+)?)")
_AMOUNT_CREDIT_RE = re.compile(r"(\d{2,6})\s*(?:credits?|刀|额度|points?|баллов)", re.IGNORECASE)

# Open-source relay engines these services are typically built on.
# Strict markers only (hyphenated names / repo authors / admin-panel titles) to
# avoid false positives like "...in one API call..." on unrelated sites.
ENGINE_BODY_MARKS = {
    "new-api": ("new-api", "newapi", "calcium-ion"),
    "one-api": ("one-api", "songquanpeng"),
    "sub2api": ("sub2api", "sub-2-api"),
    "cliproxyapi": ("cliproxyapi", "cli-proxy-api"),
}
# Admin panels of these engines set an exact <title>.
ENGINE_TITLE_EXACT = {
    "new api": "new-api",
    "one api": "one-api",
    "sub2api": "sub2api",
}


def detect_models(text: str) -> list[str]:
    """Return canonical model labels found in *text*.

    Uses two matching strategies:
    - Substring match for long, distinctive tokens (claude, gemini, deepseek …)
    - Word-boundary regex for short/ambiguous tokens (gpt, o1, o3, glm) to
      avoid false positives like "egypt" → gpt or "o1" inside a version string.
    """
    blob = (text or "").lower()
    out: list[str] = []
    # Substring pass — long tokens, safe without boundaries.
    for kw, label in _SUBSTR_TOKENS.items():
        if kw in blob and label not in out:
            out.append(label)
    # Boundary pass — short tokens, require non-letter on both sides.
    for _token, (rx, label) in _EXACT_RES.items():
        if label not in out and rx.search(blob):
            out.append(label)
    return out


def detect_amount(text: str) -> Optional[float]:
    """Largest plausible FREE-credit amount, only when a trigger word sits next
    to the number (avoids grabbing random page figures like revenue/$80,170)."""
    t = text or ""
    low = t.lower()
    triggers = (
        "free", "credit", "trial", "bonus", "gift", "voucher", "sign up", "signup",
        "get $", "claim", "注册送", "免费", "送", "额度", "赠", "бесплатн", "кредит", "триал",
    )
    best: Optional[float] = None
    for rx in (_AMOUNT_USD_RE, _AMOUNT_CREDIT_RE):
        for m in rx.finditer(t):
            try:
                val = float(m.group(1).replace(",", "").replace(" ", ""))
            except ValueError:
                continue
            if not (1 <= val <= 5000):  # free credits are rarely above this
                continue
            window = low[max(0, m.start() - 40):m.end() + 40]
            if any(k in window for k in triggers):
                if best is None or val > best:
                    best = val
    return best


def detect_engine(text: str, headers: Optional[dict] = None) -> Optional[str]:
    # Exact admin-panel title is the most reliable signal.
    title = _title(text)
    if title and title.strip().lower() in ENGINE_TITLE_EXACT:
        return ENGINE_TITLE_EXACT[title.strip().lower()]
    blob = (text or "").lower()
    if headers:
        blob += " " + " ".join(f"{k}:{v}" for k, v in headers.items()).lower()
    for engine, marks in ENGINE_BODY_MARKS.items():
        if any(m in blob for m in marks):
            return engine
    return None

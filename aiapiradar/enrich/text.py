"""HTML text-extraction helpers shared across the enrich package.

Pure string/regex utilities used to pull a title, meta description and a
visible-text blob out of fetched HTML. No network, no package-internal deps.
"""
from __future__ import annotations

import re
from typing import Optional

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_DESC_RE = re.compile(
    r'<meta[^>]+(?:name|property)\s*=\s*["\'](?:description|og:description)["\'][^>]*'
    r'content\s*=\s*["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
_META_DESC_RE2 = re.compile(
    r'<meta[^>]+content\s*=\s*["\'](.*?)["\'][^>]*'
    r'(?:name|property)\s*=\s*["\'](?:description|og:description)["\']',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_WS_RE = re.compile(r"\s+")


def _clean_text(s: str) -> str:
    import html as _html
    return _WS_RE.sub(" ", _html.unescape(s or "")).strip()


def _visible_text(html: str, cap: int = 4000) -> str:
    no_scripts = _SCRIPT_STYLE_RE.sub(" ", html or "")
    return _clean_text(_TAG_RE.sub(" ", no_scripts))[:cap]


def _meta_description(html: str) -> Optional[str]:
    for rx in (_META_DESC_RE, _META_DESC_RE2):
        m = rx.search(html or "")
        if m:
            txt = _clean_text(m.group(1))
            if len(txt) > 20:
                return txt[:300]
    return None


def _make_description(html: str) -> Optional[str]:
    """Prefer meta/og description; fall back to the first real paragraph."""
    meta = _meta_description(html)
    if meta:
        return meta
    text = _visible_text(html, cap=400)
    return text[:280] if len(text) > 40 else None


def _title(html: str) -> Optional[str]:
    m = _TITLE_RE.search(html or "")
    return m.group(1).strip()[:200] if m else None

"""Normalization: language detection + URL/domain extraction.

Pure functions, no I/O — easy to unit test.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from ..core.signal import Signal

_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+', re.IGNORECASE)
_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# Hosts that are never the "service" itself (infra / link shorteners / social).
_SKIP_HOSTS = {
    "t.me", "youtube.com", "www.youtube.com", "youtu.be", "discord.gg",
    "discord.com", "github.com", "gist.github.com", "raw.githubusercontent.com",
    "drive.google.com", "tinyurl.com", "bit.ly",
}


def detect_lang(text: str) -> str:
    if not text:
        return "en"
    if _CJK_RE.search(text):
        return "zh"
    cyr = len(_CYRILLIC_RE.findall(text))
    lat = len(re.findall(r"[A-Za-z]", text))
    if cyr > lat:
        return "ru"
    return "en"


def canonical_domain(url_or_domain: str | None) -> str | None:
    """Lowercased registrable-ish host, www stripped. Not full PSL, good enough."""
    if not url_or_domain:
        return None
    s = url_or_domain.strip()
    if "://" not in s:
        s = "http://" + s
    host = (urlparse(s).netloc or "").lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host or None


# Multi-part public suffixes we care about (covers our dataset; not exhaustive).
_MULTI_SUFFIXES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.co", "com.cn", "com.br",
    "com.au", "co.kr", "co.jp", "co.in", "com.tr", "com.mx", "com.ar",
    "pp.ua", "co.il", "com.sg", "com.hk",
}


def registrable_domain(url_or_domain: str | None) -> str | None:
    """Registrable domain (eTLD+1), dependency-free.

    app.base44.com -> base44.com ; university.gumloop.com -> gumloop.com ;
    rappi.com.co -> rappi.com.co ; kiro.dev -> kiro.dev
    """
    host = canonical_domain(url_or_domain)
    if not host:
        return None
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    last2 = ".".join(parts[-2:])
    if last2 in _MULTI_SUFFIXES:
        return ".".join(parts[-3:])
    return last2


def extract_urls(text: str) -> list[str]:
    if not text:
        return []
    return [u.rstrip(".,);") for u in _URL_RE.findall(text)]


def extract_service_domains(signal: Signal) -> list[str]:
    """Candidate service domains for this signal, skip infra/social hosts."""
    candidates: list[str] = []
    for raw in ([signal.url] if signal.url else []) + extract_urls(signal.raw_text):
        dom = canonical_domain(raw)
        if dom and dom not in _SKIP_HOSTS and dom not in candidates:
            candidates.append(dom)
    return candidates


def normalize(signal: Signal) -> tuple[Signal, list[str]]:
    """Fill language in-place-ish and return (signal, candidate_domains)."""
    if not signal.lang:
        signal.lang = detect_lang(signal.raw_text or signal.url or "")
    domains = extract_service_domains(signal)
    if not signal.url and domains:
        signal.url = "https://" + domains[0]
    return signal, domains

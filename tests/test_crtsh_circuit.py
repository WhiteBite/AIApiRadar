"""crtsh circuit-breaker: when crt.sh rate-limits us, stop after a few failures
instead of blocking on all ~24 patterns. Mocked, deterministic, offline.
"""
from __future__ import annotations

import asyncio

import httpx

from aiapiradar.collectors.crtsh import (
    CrtshCollector,
    MAX_CONSECUTIVE_FAILS,
    SEARCH_PATTERNS,
    HARVEST_PATTERNS,
    SUBDOMAIN_PATTERNS,
)


def _patch_client(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def factory(*a, **kw):
        kw["transport"] = transport
        return real(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def test_crtsh_aborts_after_consecutive_failures(monkeypatch):
    """crt.sh 429 on every call → breaker trips, total requests are bounded."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, text="rate limited")

    _patch_client(monkeypatch, handler)

    sigs = list(asyncio.run(CrtshCollector().collect()))

    total_patterns = len(SEARCH_PATTERNS) + len(HARVEST_PATTERNS) + len(SUBDOMAIN_PATTERNS)
    assert sigs == []
    # The whole point: we DON'T issue all ~24 queries when crt.sh is rate-limiting.
    assert calls["n"] <= MAX_CONSECUTIVE_FAILS
    assert calls["n"] < total_patterns


def test_crtsh_parses_when_healthy(monkeypatch):
    """A healthy crt.sh response still yields candidate signals."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"name_value": "swiftrouter.com"}])

    _patch_client(monkeypatch, handler)
    sigs = list(asyncio.run(CrtshCollector().collect()))
    assert any(s.raw_text == "swiftrouter.com" for s in sigs)

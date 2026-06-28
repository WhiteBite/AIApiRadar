"""Integration tests for collectors migrated onto the shared fetch helper.

Each test injects an ``httpx.MockTransport`` via the collector's caller-managed
``AsyncClient`` and asserts the collector returns the expected parsed Signals
from a canned HTTP response. This locks the fetch -> parse pattern end to end
for the migrated collectors without real network I/O.
"""
from __future__ import annotations

import asyncio
import json

import httpx

from aiapiradar.collectors.appstore import AppStoreCollector
from aiapiradar.collectors.hackernews import HackerNewsCollector
from aiapiradar.collectors.openrouter import OpenRouterCollector


def _run(coro):
    return asyncio.run(coro)


def _patch_client(monkeypatch, handler) -> None:
    """Make httpx.AsyncClient(...) use our MockTransport, dropping kwargs it
    won't accept alongside a transport (headers/follow_redirects are fine to
    keep; transport overrides the network layer)."""
    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def factory(*a, **kw):
        kw["transport"] = transport
        return real(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


# --- openrouter (single GET, JSON) ----------------------------------------
def test_openrouter_collect_parses_models(monkeypatch):
    payload = {"data": [
        {"id": "deepseek/deepseek-chat", "name": "DeepSeek Chat"},
        {"id": "mistralai/mistral-7b", "name": "Mistral 7B"},
    ]}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "openrouter.ai"
        return httpx.Response(200, json=payload)

    _patch_client(monkeypatch, handler)
    sigs = list(_run(OpenRouterCollector().collect()))
    assert len(sigs) == 2
    assert all(s.source == "openrouter" for s in sigs)
    providers = {s.meta.get("provider") for s in sigs}
    assert providers == {"deepseek", "mistralai"}


def test_openrouter_collect_empty_on_500(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    _patch_client(monkeypatch, handler)
    sigs = list(_run(OpenRouterCollector().collect()))
    assert sigs == []


# --- appstore (multi-URL shared client, JSON, AI filter + dedup) ----------
def test_appstore_collect_filters_and_dedupes(monkeypatch):
    feed = {"feed": {"results": [
        {"name": "ChatGPT Assistant", "artistName": "OpenAI", "url": "https://apps.apple.com/app/1"},
        {"name": "Boring Notes", "artistName": "Someone", "url": "https://apps.apple.com/app/2"},
        {"name": "AI Photo", "artistName": "Studio", "url": "https://apps.apple.com/app/3"},
    ]}}

    def handler(request: httpx.Request) -> httpx.Response:
        # every feed URL returns the same payload -> dedup must collapse repeats
        return httpx.Response(200, json=feed)

    _patch_client(monkeypatch, handler)
    sigs = list(_run(AppStoreCollector().collect()))
    # "ChatGPT Assistant" + "AI Photo" match the AI regex; "Boring Notes" does not.
    # Three identical feeds -> deduped to the 2 unique AI apps.
    urls = {s.url for s in sigs}
    assert urls == {"https://apps.apple.com/app/1", "https://apps.apple.com/app/3"}
    assert all(s.source == "appstore" for s in sigs)


# --- hackernews (multi-URL shared client, JSON with params) ---------------
def test_hackernews_collect_parses_hits(monkeypatch):
    hit_payload = {"hits": [
        {"title": "Free API credits for all", "url": "https://example.com/promo",
         "objectID": "42", "points": 10},
    ]}
    seen_tags: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_tags.append(request.url.params.get("tags", ""))
        return httpx.Response(200, json=hit_payload)

    _patch_client(monkeypatch, handler)
    # one query keeps the test fast and deterministic
    sigs = list(_run(HackerNewsCollector(queries=["free credits api"]).collect()))
    # 1 keyword query + 1 show_hn sweep, each returns the single hit
    assert len(sigs) == 2
    assert all(s.source == "hackernews" for s in sigs)
    assert all(s.url == "https://example.com/promo" for s in sigs)
    assert "story" in seen_tags and "show_hn" in seen_tags

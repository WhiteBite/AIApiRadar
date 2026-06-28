"""Tests for the shared HTTP fetch helpers (aiapiradar.core.fetch).

Network is mocked with ``httpx.MockTransport`` injected via a caller-managed
``AsyncClient`` so the helpers' status/JSON/exception handling is exercised
without real I/O. Style matches the repo: plain functions + ``asyncio.run``.
"""
from __future__ import annotations

import asyncio

import httpx

from aiapiradar.core.fetch import DEFAULT_UA, fetch_json, fetch_text


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _run(coro):
    return asyncio.run(coro)


# --- fetch_json ------------------------------------------------------------
def test_fetch_json_returns_dict_on_200():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hello": "world", "n": 1})

    async def go():
        async with _client(handler) as client:
            return await fetch_json("https://example.com/api", client=client)

    data = _run(go())
    assert data == {"hello": "world", "n": 1}


def test_fetch_json_returns_none_on_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    async def go():
        async with _client(handler) as client:
            return await fetch_json("https://example.com/missing", client=client)

    assert _run(go()) is None


def test_fetch_json_returns_none_on_invalid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="this is <not> json")

    async def go():
        async with _client(handler) as client:
            return await fetch_json("https://example.com/bad", client=client)

    assert _run(go()) is None


# --- fetch_text ------------------------------------------------------------
def test_fetch_text_returns_body_on_200():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="hello body")

    async def go():
        async with _client(handler) as client:
            return await fetch_text("https://example.com/page", client=client)

    assert _run(go()) == "hello body"


def test_fetch_text_returns_none_on_500():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    async def go():
        async with _client(handler) as client:
            return await fetch_text("https://example.com/err", client=client)

    assert _run(go()) is None


# --- exceptions are guarded ------------------------------------------------
def test_both_return_none_when_transport_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async def go():
        async with _client(handler) as client:
            t = await fetch_text("https://example.com/x", client=client)
            j = await fetch_json("https://example.com/x", client=client)
            return t, j

    t, j = _run(go())
    assert t is None
    assert j is None


# --- UA + params are forwarded --------------------------------------------
def test_default_ua_and_params_forwarded():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent", "")
        seen["q"] = request.url.params.get("q", "")
        return httpx.Response(200, json={"ok": True})

    async def go():
        async with _client(handler) as client:
            return await fetch_json(
                "https://example.com/s", params={"q": "hi"}, client=client
            )

    assert _run(go()) == {"ok": True}
    assert seen["ua"] == DEFAULT_UA
    assert seen["q"] == "hi"


def test_caller_headers_override_ua():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, text="ok")

    async def go():
        async with _client(handler) as client:
            return await fetch_text(
                "https://example.com/s",
                headers={"User-Agent": "Custom/9.9"},
                client=client,
            )

    assert _run(go()) == "ok"
    assert seen["ua"] == "Custom/9.9"

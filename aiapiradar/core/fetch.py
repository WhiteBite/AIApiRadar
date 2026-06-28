"""Shared async HTTP fetch helpers.

Most collectors share the same "open client → GET → check 200 → parse" plumbing.
These two helpers centralise that boilerplate AND the error handling: a non-200
response or ANY exception (network/timeout/JSON) is swallowed and turns into
``None`` so a collector never crashes on a transient failure — it just gets no
data for that URL and moves on.

Two usage modes:

* **caller-managed client** — pass ``client=`` (e.g. a collector that loops over
  several URLs with one shared ``AsyncClient``). The helper uses it as-is and
  never closes it; lifecycle stays with the caller.
* **one-shot** — omit ``client``; the helper opens a short-lived
  ``AsyncClient(timeout=timeout, follow_redirects=True)`` in a context manager
  and closes it before returning.

The default ``User-Agent`` is always sent, merged into ``headers`` so a caller
can override it (e.g. a browser-like UA for scraper sources).
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

import httpx

from ..logging_conf import get_logger

log = get_logger("fetch")

DEFAULT_UA = "AiApiRadar/0.1"


def _merge_headers(headers: Optional[Mapping[str, str]], ua: str) -> dict[str, str]:
    """Return headers with ``User-Agent: ua`` applied first so caller wins."""
    merged: dict[str, str] = {"User-Agent": ua}
    if headers:
        merged.update(headers)
    return merged


async def _get(
    url: str,
    *,
    timeout: float,
    headers: Optional[Mapping[str, str]],
    params: Optional[Mapping[str, Any]],
    client: Optional[httpx.AsyncClient],
    ua: str,
) -> Optional[httpx.Response]:
    """GET *url* and return the Response, or None on non-200 / any error.

    Reuses *client* if given (caller owns its lifecycle); otherwise opens a
    short-lived ``AsyncClient(follow_redirects=True)`` and closes it.
    """
    merged = _merge_headers(headers, ua)
    try:
        if client is not None:
            resp = await client.get(url, headers=merged, params=params)
        else:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
                resp = await c.get(url, headers=merged, params=params)
        if resp.status_code != 200:
            log.warning("fetch %s -> %s", url, resp.status_code)
            return None
        return resp
    except Exception:
        log.warning("fetch %s failed", url, exc_info=False)
        return None


async def fetch_text(
    url: str,
    *,
    timeout: float = 25.0,
    headers: Optional[Mapping[str, str]] = None,
    params: Optional[Mapping[str, Any]] = None,
    client: Optional[httpx.AsyncClient] = None,
    ua: str = DEFAULT_UA,
) -> Optional[str]:
    """GET *url* → response text, or None on non-200 / any error (guarded).

    Reuses *client* if given (caller manages its lifecycle); otherwise opens a
    short-lived ``AsyncClient(follow_redirects=True)``. Always sends the UA
    header, merged so caller-supplied headers can override it.
    """
    resp = await _get(
        url, timeout=timeout, headers=headers, params=params, client=client, ua=ua
    )
    if resp is None:
        return None
    try:
        return resp.text
    except Exception:
        log.warning("fetch %s: reading text failed", url, exc_info=False)
        return None


async def fetch_json(
    url: str,
    *,
    timeout: float = 25.0,
    headers: Optional[Mapping[str, str]] = None,
    params: Optional[Mapping[str, Any]] = None,
    client: Optional[httpx.AsyncClient] = None,
    ua: str = DEFAULT_UA,
) -> Optional[Any]:
    """GET *url* → parsed JSON, or None on non-200 / invalid JSON / any error.

    Same client/UA semantics as :func:`fetch_text`.
    """
    resp = await _get(
        url, timeout=timeout, headers=headers, params=params, client=client, ua=ua
    )
    if resp is None:
        return None
    try:
        return resp.json()
    except Exception:
        log.warning("fetch %s: invalid JSON", url, exc_info=False)
        return None

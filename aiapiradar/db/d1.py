"""D1Database — Cloudflare D1 REST API implementation of Database Protocol.

D1 uses ? placeholders (identical to SQLite), so existing SQL is fully
portable between local and cloudflare platforms.

API reference:
  POST /client/v4/accounts/{account_id}/d1/database/{database_id}/query
  Body:  {"sql": "...", "params": [...]}
  Reply: {"result": [{"results": [...], "success": true}], "success": true}
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Sequence

import httpx

from ..config import get_settings


class D1Database:
    """Implements the Database Protocol against the Cloudflare D1 REST API.

    All operations auto-commit; commit() and rollback() are intentional no-ops
    because D1 commits every query automatically and does not expose manual
    transaction control over the REST interface.
    """

    def __init__(
        self,
        account_id: str,
        database_id: str,
        api_token: str,
    ) -> None:
        self._url = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
            f"/d1/database/{database_id}/query"
        )
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    def _query(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        """Execute a single SQL statement against the D1 REST endpoint.

        Raises:
            httpx.HTTPStatusError: on non-2xx HTTP responses.
            RuntimeError: when the D1 API reports success=false.
        """
        resp = httpx.post(
            self._url,
            headers=self._headers,
            json={"sql": sql, "params": params or []},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"D1 error: {data}")
        results = data.get("result", [])
        if results:
            return results[0].get("results", [])
        return []

    def execute(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        """Run a SELECT, return rows as list of dicts."""
        return self._query(sql, list(params))

    def run(self, sql: str, params: Sequence[Any] = ()) -> None:
        """Run INSERT / UPDATE / DELETE."""
        self._query(sql, list(params))

    def runmany(self, sql: str, params_list: Sequence[Sequence[Any]]) -> None:
        """Run INSERT / UPDATE for multiple rows."""
        for params in params_list:
            self._query(sql, list(params))

    def commit(self) -> None:
        """No-op: D1 auto-commits every query."""

    def rollback(self) -> None:
        """No-op: D1 does not support manual rollback via the REST API."""


@contextmanager
def d1_db_factory() -> Iterator[D1Database]:
    """Context manager that yields a D1Database.

    Registered as the db factory when AIRADAR_PLATFORM=cloudflare.
    Credentials are read from config (CF_ACCOUNT_ID, CF_D1_DATABASE_ID,
    CF_API_TOKEN).
    """
    settings = get_settings()
    db = D1Database(
        account_id=settings.cf_account_id,
        database_id=settings.cf_d1_database_id,
        api_token=settings.cf_api_token,
    )
    try:
        yield db
    except Exception:
        raise

"""Watchdog: re-probe known services so the feed reflects reality.

Relay services die within weeks; this keeps status/reliability current and
re-scores offers afterwards. Picks services never checked or checked longer
than `stale_hours` ago.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import httpx

from .db import get_db
from .enrich import enrich_service
from .logging_conf import get_logger
from .models import utcnow
from .scorer import rescore_all

log = get_logger("watchdog")


def _dt_str(d: Optional[dt.datetime]) -> Optional[str]:
    """Datetime → storage string (naive UTC, SQLAlchemy-compatible format)."""
    if d is None:
        return None
    if d.tzinfo is not None:
        d = d.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return d.strftime("%Y-%m-%d %H:%M:%S.%f")


async def run_watchdog(
    limit: Optional[int] = 50,
    stale_hours: float = 24.0,
    timeout: float = 10.0,
    with_crtsh: bool = True,
) -> int:
    cutoff_str = _dt_str(utcnow() - dt.timedelta(hours=stale_hours))

    with get_db() as db:
        sql = (
            "SELECT id, canonical_domain FROM services "
            "WHERE last_checked IS NULL OR last_checked < ? "
            # also (re)enrich services whose offers still lack a description,
            # so the blurb/models backfill completes even when status is fresh
            "OR id IN (SELECT service_id FROM offers WHERE description IS NULL)"
        )
        params: list = [cutoff_str]
        if limit:
            sql += " LIMIT ?"
            params.append(limit)

        rows = db.execute(sql, params)
        if not rows:
            log.info("watchdog: nothing stale to check")
            return 0

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 AiApiRadar/0.1"},
        ) as client:
            for row in rows:
                try:
                    await enrich_service(db, row["id"], client, do_crtsh=with_crtsh)
                except Exception:
                    log.warning("watchdog enrich failed: %s", row["canonical_domain"])

        rescore_all(db)
        log.info("watchdog checked %d services", len(rows))
        return len(rows)

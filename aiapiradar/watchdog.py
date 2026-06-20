"""Watchdog: re-probe known services so the feed reflects reality.

Relay services die within weeks; this keeps status/reliability current and
re-scores offers afterwards. Picks services never checked or checked longer
than `stale_hours` ago.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import httpx
from sqlalchemy import or_, select

from .db import session_scope
from .enrich import enrich_service
from .logging_conf import get_logger
from .models import Service, utcnow
from .scorer import rescore_all

log = get_logger("watchdog")


async def run_watchdog(limit: Optional[int] = 50, stale_hours: float = 24.0,
                       timeout: float = 20.0) -> int:
    cutoff = utcnow() - dt.timedelta(hours=stale_hours)
    with session_scope() as session:
        stmt = select(Service).where(
            or_(Service.last_checked.is_(None), Service.last_checked < cutoff)
        )
        if limit:
            stmt = stmt.limit(limit)
        services = session.scalars(stmt).all()
        if not services:
            log.info("watchdog: nothing stale to check")
            return 0
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 AiApiRadar/0.1"},
        ) as client:
            for svc in services:
                try:
                    await enrich_service(session, svc, client)
                except Exception:
                    log.warning("watchdog enrich failed: %s", svc.canonical_domain)
        rescore_all(session)
        log.info("watchdog checked %d services", len(services))
        return len(services)

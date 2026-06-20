"""Scheduler skeleton.

Phase 0: wiring only. It discovers registered collectors and schedules them on
their declared intervals. The pipeline hook is a stub until Phase 1/2.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Iterable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .collectors import get_registry, load_builtin
from .core.signal import Signal
from .logging_conf import get_logger

log = get_logger("scheduler")

# Pipeline callback: receives signals from a collector run. Replaced in Phase 1.
PipelineFn = Callable[[Iterable[Signal]], Awaitable[None]]


async def _default_pipeline(signals: Iterable[Signal]) -> None:
    # Lazy import to avoid a hard dependency when only scheduling is needed.
    from .pipeline import async_pipeline

    await async_pipeline(signals)


async def run_collector_once(name: str, cls, pipeline: PipelineFn) -> None:
    collector = cls()
    try:
        signals = await collector.collect()
        await pipeline(signals)
    except Exception:  # pragma: no cover - defensive
        log.exception("collector %s failed", name)


def build_scheduler(pipeline: PipelineFn | None = None) -> AsyncIOScheduler:
    pipeline = pipeline or _default_pipeline
    load_builtin()
    scheduler = AsyncIOScheduler()
    registry = get_registry()
    if not registry:
        log.warning("no collectors registered yet")
    for name, cls in registry.items():
        interval = getattr(cls, "interval", 900)
        scheduler.add_job(
            run_collector_once,
            "interval",
            seconds=interval,
            args=[name, cls, pipeline],
            id=name,
            max_instances=1,
            coalesce=True,
        )
        log.info("scheduled collector %s every %ds", name, interval)

    # Maintenance jobs: keep service status fresh and re-score the feed.
    async def _watchdog_job() -> None:
        from .watchdog import run_watchdog
        await run_watchdog(limit=50, stale_hours=24.0)

    scheduler.add_job(_watchdog_job, "interval", hours=6, id="watchdog",
                      max_instances=1, coalesce=True)
    log.info("scheduled watchdog every 6h")

    async def _notify_job() -> None:
        from .notifier import notify_new_offers
        await notify_new_offers(limit=20)

    scheduler.add_job(_notify_job, "interval", minutes=10, id="notify",
                      max_instances=1, coalesce=True)
    log.info("scheduled notifier every 10m")
    return scheduler


async def run_forever(pipeline: PipelineFn | None = None) -> None:  # pragma: no cover
    scheduler = build_scheduler(pipeline)
    scheduler.start()
    log.info("scheduler started; press Ctrl+C to stop")
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

"""APScheduler-based scheduler implementation.

Phase 0: wiring only. It discovers registered collectors and schedules them on
their declared intervals. The pipeline hook is a stub until Phase 1/2.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Iterable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..collectors import get_registry, load_builtin
from ..core.signal import Signal
from ..logging_conf import get_logger

log = get_logger("scheduler")

# Pipeline callback: receives signals from a collector run. Replaced in Phase 1.
PipelineFn = Callable[[Iterable[Signal]], Awaitable[None]]


async def _default_pipeline(signals: Iterable[Signal]) -> None:
    # Lazy import to avoid a hard dependency when only scheduling is needed.
    from ..pipeline import async_pipeline

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

    # Config layer: only schedule collectors enabled in the `sources` table,
    # and honour any per-collector interval override stored there.
    from ..config import get_settings
    from .source_config import enabled_collectors, resolve_interval, sync_sources

    settings = get_settings()
    registry = get_registry()
    sync_sources(registry)  # ensure every collector has a sources row
    registry = enabled_collectors(registry)

    if not registry:
        log.warning("no enabled collectors registered")
    for name, cls in registry.items():
        # Stream collectors (persistent websockets) only make sense on the VDS
        # process runner; skip them entirely when streaming is disabled.
        if getattr(cls, "mode", "poll") == "stream" and not settings.enable_streaming:
            log.info("skipping stream collector %s (streaming disabled)", name)
            continue
        interval = resolve_interval(name, cls)
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
        from ..watchdog import run_watchdog
        await run_watchdog(limit=50, stale_hours=24.0)

    scheduler.add_job(_watchdog_job, "interval", hours=6, id="watchdog",
                      max_instances=1, coalesce=True)
    log.info("scheduled watchdog every 6h")

    # Discovery: probe domains harvested from signals and promote real services.
    # Runs often (new candidates accumulate on every collector pass) but each
    # run is bounded by `limit`, so the probe load stays predictable. Gated by
    # settings.enable_discovery so operators can turn the worker off entirely.
    if settings.enable_discovery:
        async def _discover_job() -> None:
            from ..discover import run_discovery
            await run_discovery(limit=settings.discovery_limit,
                                timeout=settings.probe_timeout)

        scheduler.add_job(_discover_job, "interval", minutes=20, id="discover",
                          max_instances=1, coalesce=True)
        log.info("scheduled discovery every 20m")
    else:
        log.info("discovery disabled (enable_discovery=False)")

    async def _notify_job() -> None:
        from ..notifier import notify_new_offers
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

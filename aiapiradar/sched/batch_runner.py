"""Batch runner — the serverless / CI one-shot execution path.

Runs a SINGLE pass with no APScheduler: every enabled poll collector runs once,
then maintenance (enrich/watchdog, discovery, notify) runs once. This is what
Cloudflare cron Workers and GitHub Actions invoke — they wake up, do one pass,
and exit.

Contrast with the process runner (apscheduler_impl), which keeps a long-lived
loop alive on a VDS and is the only place stream collectors (persistent
websockets) can run. The batch runner deliberately SKIPS stream collectors.
"""
from __future__ import annotations

import asyncio

from ..config import get_settings
from ..core.budget import RunBudget
from ..logging_conf import get_logger
from .source_config import enabled_collectors, sync_sources

log = get_logger("batch_runner")


async def run_batch(budget=None) -> dict:
    """Execute one full collect + maintenance pass.

    Args:
        budget: optional :class:`RunBudget` capping outbound work this pass
            (subrequests / wall-clock / discovery probes). ``None`` builds one
            from settings via :meth:`RunBudget.from_settings` — so on a VDS it
            is effectively unbounded, and on Cloudflare it honours the
            configured ``max_subrequests`` / ``discovery_limit``.

            For backward compatibility a legacy ``int`` is still accepted and
            treated as a crude "max number of poll collectors" cap (this is how
            ``cli.py collect-once --limit`` calls it).

    Returns a stats dict summarising the pass. Individual collector failures
    are swallowed by ``run_collector_once`` so one bad source never aborts the
    batch.
    """
    from ..collectors import get_registry, load_builtin
    # Imported lazily so this module stays importable without APScheduler wiring
    # side effects; reuses the exact same per-collector logic as the VDS path.
    from .apscheduler_impl import _default_pipeline, run_collector_once

    # Legacy int budget = "max collectors" cap (old CLI contract). Peel it off
    # before resolving the real RunBudget so both call styles keep working.
    collector_cap: int | None = None
    if isinstance(budget, int):
        collector_cap = budget if budget > 0 else None
        budget = None

    budget = budget or RunBudget.from_settings()

    settings = get_settings()
    stats: dict = {
        "collectors_run": 0,
        "collectors_skipped_stream": 0,
        "collectors_disabled": 0,
        "enrich": 0,
        "discovery": None,
        "notified": 0,
        "budget": {
            "max_subrequests": budget.max_subrequests,
            "max_seconds": budget.max_seconds,
            "max_probes": budget.max_probes,
        },
    }

    load_builtin()
    registry = get_registry()
    sync_sources(registry)

    enabled = enabled_collectors(registry)
    stats["collectors_disabled"] = len(registry) - len(enabled)

    # Batch never runs stream collectors — they need a long-lived process.
    poll = {}
    for name, cls in enabled.items():
        if getattr(cls, "mode", "poll") == "poll":
            poll[name] = cls
        else:
            stats["collectors_skipped_stream"] += 1

    names = list(poll.keys())
    # Collectors aren't the main subrequest cost, so the RunBudget doesn't cap
    # them; only the legacy int budget (if supplied) trims the collector list.
    if collector_cap is not None:
        names = names[:collector_cap]

    for name in names:
        await run_collector_once(name, poll[name], _default_pipeline)
        stats["collectors_run"] += 1

    # ── Maintenance: one pass each, bounded so the batch stays predictable ──
    try:
        from ..watchdog import run_watchdog
        # with_crtsh=False: crt.sh hard-rate-limits shared CI IPs (429), so a
        # per-domain age lookup just burns the timeout for no data. The hourly
        # `enrich --no-crtsh` step covers enrichment; skip crt.sh here too.
        stats["enrich"] = await run_watchdog(limit=20, stale_hours=24.0, with_crtsh=False)
    except Exception:  # pragma: no cover - defensive, keep batch going
        log.exception("batch watchdog failed")

    if settings.enable_discovery:
        try:
            from ..discover import run_discovery
            stats["discovery"] = await run_discovery(
                limit=settings.discovery_limit,
                timeout=settings.probe_timeout,
                budget=budget,
            )
        except Exception:  # pragma: no cover - defensive
            log.exception("batch discovery failed")

    try:
        from ..notifier import notify_new_offers
        stats["notified"] = await notify_new_offers(limit=20)
    except Exception:  # pragma: no cover - defensive
        log.exception("batch notify failed")

    log.info("batch run complete: %s", stats)
    return stats


def run_batch_sync(budget=None) -> dict:
    """Synchronous wrapper for CLI / cron entry points."""
    return asyncio.run(run_batch(budget=budget))

"""Scheduler implementations + runner factory.

Two execution models share the same collectors and pipeline:

  process runner  → APScheduler loop, long-lived (VDS / Docker).
                    The ONLY runner that may host stream collectors.
  batch runner    → one-shot pass, no scheduler (serverless / CI cron).

`get_runner()` picks one based on settings (explicit `runner` override, or
`auto` → derived from `platform`). It returns a zero-arg callable that runs the
selected runner to completion (blocking for `process`, one pass for `batch`).
"""
from __future__ import annotations

from typing import Callable

from ..config import get_settings
from ..logging_conf import get_logger

log = get_logger("runner")


def _resolve_runner_kind() -> str:
    """Return "process" or "batch" from settings.runner / settings.platform."""
    settings = get_settings()
    runner = (settings.runner or "auto").lower()
    if runner in ("process", "batch"):
        return runner
    # auto → derive from platform: local hosts a long process, cloudflare is
    # serverless cron (one-shot batches).
    if runner == "auto":
        return "batch" if settings.is_cloudflare else "process"
    log.warning("unknown runner %r; defaulting to process", runner)
    return "process"


def get_runner() -> Callable[[], object]:
    """Return a zero-arg callable that executes the configured runner.

    - process → blocking APScheduler loop (``run_forever`` via asyncio.run).
    - batch   → a single collect + maintenance pass (returns a stats dict).
    """
    kind = _resolve_runner_kind()
    if kind == "batch":
        def _run_batch():
            from .batch_runner import run_batch_sync
            return run_batch_sync()
        return _run_batch

    def _run_process():
        import asyncio

        from .apscheduler_impl import run_forever
        return asyncio.run(run_forever())
    return _run_process

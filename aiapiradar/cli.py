"""Command-line entry point.

Usage:
    python -m aiapiradar.cli init-db        # create tables
    python -m aiapiradar.cli collectors     # list registered collectors
    python -m aiapiradar.cli run            # start scheduler (Phase 2+)
"""
from __future__ import annotations

import argparse
import asyncio

from .collectors import get_registry, load_builtin
from .db import init_db
from .logging_conf import get_logger

log = get_logger("cli")


def cmd_init_db(_: argparse.Namespace) -> None:
    init_db()
    log.info("database initialized")


def cmd_collectors(_: argparse.Namespace) -> None:
    load_builtin()
    registry = get_registry()
    if not registry:
        print("No collectors registered yet.")
        return
    for name, cls in sorted(registry.items()):
        print(f"  {name:16} kind={cls.kind:12} interval={cls.interval}s")


def cmd_run(_: argparse.Namespace) -> None:
    from .scheduler import run_forever

    init_db()
    asyncio.run(run_forever())


def cmd_collect_once(_: argparse.Namespace) -> None:
    """Run all collectors once — used by GitHub Actions."""
    from .pipeline import async_pipeline

    load_builtin()
    init_db()

    async def run() -> None:
        registry = get_registry()
        for name, cls in registry.items():
            try:
                collector = cls()
                signals = list(await collector.collect())
                await async_pipeline(signals)
                log.info("collector %s: %d signals", name, len(signals))
            except Exception:
                log.exception("collector %s failed", name)

    asyncio.run(run())


def cmd_enrich(args: argparse.Namespace) -> None:
    from .watchdog import run_watchdog

    init_db()
    n = asyncio.run(run_watchdog(limit=args.limit, stale_hours=args.stale_hours))
    log.info("enriched %d services", n)


def cmd_score(_: argparse.Namespace) -> None:
    from .db import session_scope
    from .scorer import rescore_all

    init_db()
    with session_scope() as session:
        n = rescore_all(session)
    log.info("rescored %d offers", n)


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    init_db()
    uvicorn.run("aiapiradar.web:app", host=args.host, port=args.port, reload=False)


def cmd_notify(args: argparse.Namespace) -> None:
    from .notifier import notify_new_offers

    init_db()
    n = asyncio.run(notify_new_offers(limit=args.limit))
    log.info("notified %d offers", n)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aiapiradar")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create database tables").set_defaults(func=cmd_init_db)
    sub.add_parser("collectors", help="list registered collectors").set_defaults(func=cmd_collectors)
    sub.add_parser("run", help="start the scheduler").set_defaults(func=cmd_run)
    sub.add_parser("collect-once", help="run all collectors once (for CI/GH Actions)").set_defaults(func=cmd_collect_once)

    p_enrich = sub.add_parser("enrich", help="probe/enrich stale services")
    p_enrich.add_argument("--limit", type=int, default=50)
    p_enrich.add_argument("--stale-hours", type=float, default=24.0)
    p_enrich.set_defaults(func=cmd_enrich)

    sub.add_parser("score", help="recompute offer scores").set_defaults(func=cmd_score)

    p_serve = sub.add_parser("serve", help="run the web dashboard + API")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=cmd_serve)

    p_notify = sub.add_parser("notify", help="push fresh high-score offers to Telegram")
    p_notify.add_argument("--limit", type=int, default=20)
    p_notify.set_defaults(func=cmd_notify)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

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
    """Run all collectors once — used by GitHub Actions / Cloudflare cron.

    Skips realtime stream/ingest collectors (certstream WebSocket, telegram
    Telethon) which are meant for the long-running scheduler. CT-log coverage
    in one-shot mode is provided by the `crtsh` HTTP-poll collector instead.
    """
    from .pipeline import async_pipeline

    skip = {"certstream", "telegram"}
    load_builtin()
    init_db()

    async def run() -> None:
        registry = get_registry()
        for name, cls in registry.items():
            if name in skip:
                continue
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


def cmd_reclassify(args: argparse.Namespace) -> None:
    """Re-classify stored offers with the LLM in BATCHES.

    Inline pipeline classification is heuristic (free, unlimited). This pass
    upgrades the small set of stored offers using the LLM, batching many
    offers per request to fit tight free-tier daily quotas (e.g. Gemini
    free-tier ~20 requests/day → ~5 batched calls covers all offers).
    """
    from .db import session_scope
    from .models import Offer, Service, Signal
    from .pipeline import normalize
    from .pipeline.classify import get_classifier
    from .scorer import rescore_all

    init_db()
    clf = get_classifier()
    log.info("reclassify using %s (batch_size=%d)", clf.__class__.__name__, args.batch_size)

    updated = 0
    with session_scope() as s:
        offers = s.query(Offer).all()
        work, items = [], []
        for o in offers:
            svc = s.get(Service, o.service_id)
            if not svc:
                continue
            sigs = s.query(Signal).filter(Signal.service_id == svc.id).all()
            texts = [x.raw_text for x in sigs if x.raw_text]
            if not texts:
                continue
            text = max(texts, key=len)
            lang = normalize.detect_lang(text)
            url = o.url or f"https://{svc.canonical_domain}"
            work.append((o, svc))
            items.append((text, url, lang, [svc.canonical_domain]))

        log.info("classifying %d offers", len(items))
        classifications = clf.classify_batch(items, batch_size=args.batch_size)

        for (o, svc), c in zip(work, classifications):
            if not c.is_offer:
                continue
            o.amount = c.amount if c.amount is not None else o.amount
            o.currency = c.currency or o.currency
            o.unit = c.unit or o.unit
            o.effort = c.effort or o.effort
            o.type = c.offer_type or o.type
            o.claim_steps = c.claim_steps or o.claim_steps
            o.requirements = c.requirements or o.requirements
            if c.models:
                o.models = c.models
            o.referral_required = bool(c.referral_required)
            updated += 1
        n = rescore_all(s)
    log.info("reclassified %d offers, rescored %d", updated, n)


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

    p_reclassify = sub.add_parser("reclassify", help="LLM-reclassify stored offers in batches (fits free-tier quotas)")
    p_reclassify.add_argument("--batch-size", type=int, default=15)
    p_reclassify.set_defaults(func=cmd_reclassify)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

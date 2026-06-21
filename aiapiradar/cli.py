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

    Collectors run CONCURRENTLY (network I/O is the bottleneck) with a per-
    collector timeout so one slow source (e.g. crt.sh) can't stall the run.
    Their signals are then pipelined sequentially (DB writes stay serial).

    Skips realtime stream/ingest collectors (certstream WebSocket, telegram
    Telethon) which are meant for the long-running scheduler. CT-log coverage
    in one-shot mode is provided by the `crtsh` HTTP-poll collector instead.
    """
    from .pipeline import async_pipeline

    skip = {"certstream", "telegram"}
    per_collector_timeout = 120.0
    load_builtin()
    init_db()

    async def run() -> None:
        registry = get_registry()
        names = [n for n in registry if n not in skip]

        async def _collect(name: str):
            try:
                collector = registry[name]()
                signals = list(await asyncio.wait_for(
                    collector.collect(), timeout=per_collector_timeout))
                log.info("collector %s: %d signals", name, len(signals))
                return signals
            except asyncio.TimeoutError:
                log.warning("collector %s timed out (%.0fs)", name, per_collector_timeout)
                return []
            except Exception:
                log.exception("collector %s failed", name)
                return []

        results = await asyncio.gather(*[_collect(n) for n in names])
        all_signals = [s for batch in results for s in batch]
        await async_pipeline(all_signals)
        log.info("collect-once: %d signals from %d collectors", len(all_signals), len(names))

    asyncio.run(run())


def cmd_enrich(args: argparse.Namespace) -> None:
    from .watchdog import run_watchdog

    init_db()
    n = asyncio.run(run_watchdog(limit=args.limit, stale_hours=args.stale_hours,
                                 with_crtsh=not args.no_crtsh))
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


def cmd_purge_blocked(_: argparse.Namespace) -> None:
    """Delete already-stored Services (and dependent rows) whose canonical
    domain is blocked — cleans data polluted before the blocklist existed.

    Removes, per blocked service: its lead_metrics (via offers), offers, and
    signals, then the service row itself. Order respects FK dependencies.
    """
    from .db import get_db, init_db
    from .pipeline.normalize import is_blocked_domain

    init_db()
    purged_services = 0
    purged_offers = 0
    purged_signals = 0
    with get_db() as db:
        services = db.execute("SELECT id, canonical_domain FROM services")
        blocked = [r for r in services if is_blocked_domain(r["canonical_domain"])]
        for svc in blocked:
            sid = svc["id"]
            offer_rows = db.execute("SELECT id FROM offers WHERE service_id = ?", [sid])
            offer_ids = [o["id"] for o in offer_rows]
            for oid in offer_ids:
                db.run("DELETE FROM lead_metrics WHERE offer_id = ?", [oid])
            sig_rows = db.execute("SELECT id FROM signals WHERE service_id = ?", [sid])
            purged_signals += len(sig_rows)
            db.run("DELETE FROM signals WHERE service_id = ?", [sid])
            db.run("DELETE FROM offers WHERE service_id = ?", [sid])
            db.run("DELETE FROM services WHERE id = ?", [sid])
            purged_offers += len(offer_ids)
            purged_services += 1
            log.info("purged blocked service %s (id=%d)", svc["canonical_domain"], sid)
        db.commit()
    log.info(
        "purge-blocked: removed %d services, %d offers, %d signals",
        purged_services, purged_offers, purged_signals,
    )


def cmd_dump_sql(args: argparse.Namespace) -> None:
    """Export all tables as DELETE + INSERT statements for a D1 reseed.

    Used by the collectors CI workflow to push the locally-collected SQLite
    state back into Cloudflare D1 (via `wrangler d1 execute --file`). Explicit
    ids are preserved so foreign-key references stay intact; DELETEs are
    prepended (reverse FK order) so the reseed is a clean replace.
    """
    from .db import get_db, init_db

    tables = ["services", "offers", "signals", "sources", "lead_metrics"]

    def esc(v: object) -> str:
        if v is None:
            return "NULL"
        if isinstance(v, bool):
            return "1" if v else "0"
        if isinstance(v, (int, float)):
            return repr(v)
        return "'" + str(v).replace("'", "''") + "'"

    init_db()
    lines = [f"DELETE FROM {t};" for t in reversed(tables)]
    with get_db() as db:
        for t in tables:
            for row in db.execute(f"SELECT * FROM {t}"):
                cols = list(row.keys())
                collist = ",".join(cols)
                vals = ",".join(esc(row[c]) for c in cols)
                lines.append(f"INSERT INTO {t} ({collist}) VALUES ({vals});")

    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    log.info("dumped %d statements to %s", len(lines), args.output)


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
    p_enrich.add_argument("--no-crtsh", action="store_true",
                          help="skip slow crt.sh domain-age lookups (fast page-only enrich)")
    p_enrich.set_defaults(func=cmd_enrich)

    sub.add_parser("score", help="recompute offer scores").set_defaults(func=cmd_score)

    sub.add_parser(
        "purge-blocked",
        help="delete stored services on blocklisted domains (clean polluted data)",
    ).set_defaults(func=cmd_purge_blocked)

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

    p_dump = sub.add_parser("dump-sql", help="export all tables as DELETE+INSERT SQL (for D1 reseed)")
    p_dump.add_argument("--output", default="seed.sql")
    p_dump.set_defaults(func=cmd_dump_sql)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

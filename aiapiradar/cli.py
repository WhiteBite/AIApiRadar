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


def cmd_collect_once(args: argparse.Namespace) -> None:
    """Run one full batch pass — used by GitHub Actions / Cloudflare cron.

    Delegates to the batch runner: every enabled poll collector runs once
    (stream collectors like certstream/telegram are skipped — they need the
    long-running scheduler), then maintenance (enrich/watchdog, discovery,
    notify) runs once. One pass, no APScheduler.

    `--limit` caps how many collectors run this pass (a simple subrequest
    budget for serverless); omit it to run them all.
    """
    from .sched.batch_runner import run_batch

    init_db()
    budget = getattr(args, "limit", None)
    stats = asyncio.run(run_batch(budget=budget))
    log.info("collect-once (batch): %s", stats)


def cmd_enrich(args: argparse.Namespace) -> None:
    from .watchdog import run_watchdog

    init_db()
    n = asyncio.run(run_watchdog(limit=args.limit, stale_hours=args.stale_hours,
                                 with_crtsh=not args.no_crtsh))
    log.info("enriched %d services", n)


def cmd_discover(args: argparse.Namespace) -> None:
    """Probe harvested domain candidates and promote real AI services.

    Discovers services we've never heard of: every domain mentioned in any
    collected signal is harvested into domain_candidates by the pipeline; this
    command probes the pending ones and promotes qualifying offers into the
    feed.
    """
    from .discover import run_discovery

    init_db()
    stats = asyncio.run(run_discovery(limit=args.limit, max_attempts=args.max_attempts))
    log.info("discover: %s", stats)


def cmd_score(_: argparse.Namespace) -> None:
    from .db import get_db
    from .scorer import rescore_all

    init_db()
    with get_db() as db:
        n = rescore_all(db)
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
    from .db import get_db
    from .db.base import json_encode, json_decode
    from .pipeline import normalize
    from .pipeline.classify import get_classifier
    from .scorer import rescore_all

    init_db()
    clf = get_classifier()
    log.info("reclassify using %s (batch_size=%d)", clf.__class__.__name__, args.batch_size)

    MAX_USD = 5000.0
    MAX_CREDITS = 5000.0
    updated = 0

    with get_db() as db:
        # Load offers + services in one join
        rows = db.execute("""
            SELECT o.id, o.service_id, o.type, o.amount, o.currency, o.unit,
                   o.effort, o.models, o.claim_steps, o.requirements, o.referral_required,
                   s.canonical_domain
            FROM offers o
            JOIN services s ON o.service_id = s.id
        """)

        # Load all signals, keyed by service_id
        sig_rows = db.execute("SELECT service_id, raw_text, lang FROM signals WHERE raw_text IS NOT NULL")
        sigs_by_svc: dict = {}
        for sr in sig_rows:
            sid = sr["service_id"]
            if sid:
                sigs_by_svc.setdefault(sid, []).append(sr)

        # Build classify inputs for offers that have signal text
        work = []   # (offer_row_dict,)
        items = []  # (text, url, lang, domains)
        for o in rows:
            sigs = sigs_by_svc.get(o["service_id"], [])
            texts = [s["raw_text"] for s in sigs if s["raw_text"]]
            if not texts:
                continue
            text = max(texts, key=len)
            lang = normalize.detect_lang(text)
            url = f"https://{o['canonical_domain']}"
            work.append(o)
            items.append((text, url, lang, [o["canonical_domain"]]))

        log.info("classifying %d offers", len(items))
        classifications = clf.classify_batch(items, batch_size=args.batch_size)

        for o, c in zip(work, classifications):
            if not c.is_offer:
                continue
            llm_amount = c.amount
            if llm_amount is not None:
                cap = MAX_CREDITS if c.unit == "credits" else MAX_USD
                if llm_amount > cap:
                    llm_amount = None

            # Build UPDATE: only overwrite if LLM gave a non-None value
            fields, params = [], []
            if llm_amount is not None:
                fields.append("amount=?"); params.append(llm_amount)
            if c.currency:
                fields.append("currency=?"); params.append(c.currency)
            if c.unit:
                fields.append("unit=?"); params.append(c.unit)
            if c.effort:
                fields.append("effort=?"); params.append(c.effort)
            if c.offer_type:
                fields.append("type=?"); params.append(c.offer_type)
            if c.claim_steps:
                fields.append("claim_steps=?"); params.append(c.claim_steps)
            if c.requirements:
                fields.append("requirements=?"); params.append(c.requirements)
            if c.models:
                fields.append("models=?"); params.append(json_encode(c.models))
            if c.conditions:
                fields.append("conditions=?"); params.append(json_encode(c.conditions))
            fields.append("referral_required=?"); params.append(int(c.referral_required))
            if fields:
                params.append(o["id"])
                db.run(f"UPDATE offers SET {', '.join(fields)} WHERE id=?", params)
                updated += 1

        n = rescore_all(db)

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


def cmd_lead_report(args: argparse.Namespace) -> None:
    """Print a lead-time scoreboard: how many hours ahead of TG aggregators we are."""
    from .db import get_db

    init_db()
    with get_db() as db:
        rows = db.execute(
            "SELECT lm.lead_hours, lm.offer_id, lm.first_seen_by_us, "
            "lm.first_seen_in_aggregator, "
            "s.canonical_domain "
            "FROM lead_metrics lm "
            "JOIN offers o ON lm.offer_id = o.id "
            "JOIN services s ON o.service_id = s.id "
            "WHERE lm.lead_hours IS NOT NULL "
            "ORDER BY lm.lead_hours DESC"
        )

    if not rows:
        print("No lead-time data yet. Run the pipeline with Telegram ingest enabled.")
        return

    hours = [r["lead_hours"] for r in rows]
    ahead  = [h for h in hours if h > 0]
    behind = [h for h in hours if h < 0]
    tied   = [h for h in hours if h == 0]

    avg = round(sum(hours) / len(hours), 1) if hours else 0
    s_h = sorted(hours)
    mid = len(s_h) // 2
    median = round((s_h[mid-1]+s_h[mid])/2 if len(s_h)%2==0 else s_h[mid], 1)

    print(f"\n{'='*55}")
    print(f"  Lead-time scoreboard  ({len(rows)} offers tracked)")
    print(f"{'='*55}")
    print(f"  Ahead of aggregators : {len(ahead):>4}  ({100*len(ahead)//len(rows)}%)")
    print(f"  Behind aggregators   : {len(behind):>4}  ({100*len(behind)//len(rows)}%)")
    print(f"  Tied                 : {len(tied):>4}")
    print(f"  Average lead         : {avg:>+.1f} h")
    print(f"  Median lead          : {median:>+.1f} h")
    if ahead:
        best = max(ahead)
        best_domain = next((r["canonical_domain"] for r in rows if r["lead_hours"]==best), "?")
        print(f"  Best lead            : {best:>+.1f} h  ({best_domain})")
    print()

    # Top-10 by lead time
    top = sorted(rows, key=lambda r: r["lead_hours"], reverse=True)[:10]
    print(f"  {'Domain':<35} {'Lead (h)':>9}  First seen by us")
    print(f"  {'-'*35} {'-'*9}  {'-'*20}")
    for r in top:
        first_us = (r["first_seen_by_us"] or "")[:16]
        print(f"  {r['canonical_domain']:<35} {r['lead_hours']:>+9.1f}  {first_us}")
    print()


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
    p_collect = sub.add_parser("collect-once", help="run one batch pass: all enabled poll collectors + maintenance (for CI/cron)")
    p_collect.add_argument("--limit", type=int, default=None,
                           help="cap how many collectors run this pass (subrequest budget); default: all")
    p_collect.set_defaults(func=cmd_collect_once)

    p_enrich = sub.add_parser("enrich", help="probe/enrich stale services")
    p_enrich.add_argument("--limit", type=int, default=50)
    p_enrich.add_argument("--stale-hours", type=float, default=24.0)
    p_enrich.add_argument("--no-crtsh", action="store_true",
                          help="skip slow crt.sh domain-age lookups (fast page-only enrich)")
    p_enrich.set_defaults(func=cmd_enrich)

    p_discover = sub.add_parser(
        "discover",
        help="probe harvested domain candidates, promote new AI services",
    )
    p_discover.add_argument("--limit", type=int, default=40,
                            help="max candidates to probe per run")
    p_discover.add_argument("--max-attempts", type=int, default=3,
                            help="give up on a candidate after this many failed probes")
    p_discover.set_defaults(func=cmd_discover)

    sub.add_parser("score", help="recompute offer scores").set_defaults(func=cmd_score)

    sub.add_parser(
        "purge-blocked",
        help="delete stored services on blocklisted domains (clean polluted data)",
    ).set_defaults(func=cmd_purge_blocked)

    sub.add_parser(
        "lead-report",
        help="print lead-time scoreboard (how many hours ahead of TG aggregators)",
    ).set_defaults(func=cmd_lead_report)

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

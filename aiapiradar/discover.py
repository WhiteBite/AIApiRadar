"""Discovery worker: probe harvested domain candidates, promote real services.

Discovery is decoupled from classification. The pipeline harvests every domain
mentioned in any signal into `domain_candidates` (see pipeline._harvest_domains)
BEFORE the prefilter can drop the signal. This worker takes the pending
candidates, probes each with enrich.probe(), and promotes the ones that look
like a real AI service with a free/trial offer into `services` (status 'new'),
where the normal watchdog → enrich → scorer flow picks them up.

This is how we find services we've never heard of: a mention anywhere we
already listen → candidate → probe → promote. No prior knowledge of the domain
and no AI keyword in its name required (unlike certstream/crtsh).

Reuses the existing enrich.probe() qualification engine — this worker only
decides what to probe and what to keep.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import time
from typing import Optional

import httpx

from .core.budget import RunBudget
from .db import get_db
from .db.base import json_encode
from .enrich import ProbeResult, probe
from .logging_conf import get_logger
from .models import utcnow
from .pipeline.normalize import (
    extract_urls,
    is_blocked_domain,
    registrable_domain,
)

log = get_logger("discover")

# Link-graph expansion: when a candidate is promoted to a real service, that
# service's own pages usually list the providers it routes to / alternatives /
# partner links. We crawl a few of its pages, harvest the outbound registrable
# domains we've never seen, and queue them as fresh 'linkgraph' candidates so
# the discovery network expands itself. Best-effort: every fetch is guarded and
# can never fail the run or block a promotion.
_LINKGRAPH_PATHS = ("/", "/models", "/providers", "/docs")
# Hard ceiling on promoted-service crawls per run (further shrunk by the budget).
_LINKGRAPH_MAX_CRAWLS = 10

# Exponential backoff before re-probing a domain that already failed.
# Index is (attempts - 1), clamped to the last entry for higher attempt counts.
# attempts=1 → wait at least 1 h, attempts=2 → 6 h, attempts≥3 → 24 h.
_MIN_RETRY_HOURS: list[float] = [1.0, 6.0, 24.0]

# SSRF / abuse guard: never probe private, loopback or non-public hosts.
_BLOCK_PROBE_SUFFIXES = (".local", ".internal", ".lan", ".localdomain")
_BLOCK_PROBE_EXACT = {"localhost"}


def _dt_str(d: Optional[dt.datetime]) -> Optional[str]:
    if d is None:
        return None
    if d.tzinfo is not None:
        d = d.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return d.strftime("%Y-%m-%d %H:%M:%S.%f")


def _should_skip_retry(attempts: int, probed_at: Optional[str]) -> bool:
    """Return True if the domain was probed too recently to retry now.

    Uses an exponential back-off table: the first retry waits 1 h, the second
    6 h, and any further retries 24 h.  A domain that has never been probed
    (attempts=0) is always eligible.
    """
    if attempts == 0 or probed_at is None:
        return False  # never probed — go ahead immediately
    idx = min(attempts - 1, len(_MIN_RETRY_HOURS) - 1)
    min_hours = _MIN_RETRY_HOURS[idx]
    try:
        # Stored as "YYYY-MM-DD HH:MM:SS.ffffff" (SQLite naive-UTC string).
        last = dt.datetime.fromisoformat(probed_at.replace(" ", "T"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=dt.timezone.utc)
        elapsed_hours = (utcnow() - last).total_seconds() / 3600.0
        return elapsed_hours < min_hours
    except Exception:
        return False  # unparseable timestamp — don't block the probe


def _safe_to_probe(domain: str) -> bool:
    """Reject loopback / private / IP-literal hosts before making a request."""
    if not domain or "." not in domain:
        return False
    if domain in _BLOCK_PROBE_EXACT:
        return False
    if any(domain.endswith(s) for s in _BLOCK_PROBE_SUFFIXES):
        return False
    if domain.replace(".", "").isdigit():  # bare IPv4 literal
        return False
    return True


def should_promote(p: ProbeResult) -> bool:
    """Decide if a probed domain is a real AI service worth tracking.

    Conservative on purpose — false promotes pollute the feed. Two gates:

      1. AI relevance — the page must look like an AI/LLM product: detected
         model names (claude/gpt/gemini/...) or an LLM-gateway engine. This is
         what stops false positives like tempmail.so / fakeiban.org, which have
         a /pricing page with the word "free" but no AI signal at all.
      2. Offer/pricing signal — a free-credit trigger, a detected amount, or a
         pricing page (so we don't promote a bare landing page).
    """
    if not p.alive:
        return False
    # AI signal: known model detected, relay engine identified, or is_relay=True.
    # is_relay=True means the domain answered /api/status or /v1/models in relay
    # format — that IS an AI service even when no model keywords were found (e.g.
    # a Chinese-only relay with obscure local model IDs like "qwq-plus-0919").
    ai_signal = bool(p.models) or bool(getattr(p, "engine", None)) or p.is_relay
    if not ai_signal:
        return False
    # A confirmed relay (answered /api/status or /v1/models) is a live LLM
    # gateway by definition — promoting it doesn't require a separate offer
    # trigger because the live /v1/models endpoint IS the offer.
    if p.is_relay:
        return True
    offer_signal = bool(p.pricing_triggers) or (p.amount is not None) or p.has_pricing
    return offer_signal


def _summary(p: ProbeResult) -> str:
    return json_encode({
        "alive": p.alive, "status": p.status, "title": p.title,
        "engine": p.engine, "has_pricing": p.has_pricing,
        "pricing_triggers": p.pricing_triggers, "models": p.models,
        "amount": p.amount,
    }) or "{}"


def _promote(db, domain: str, p: ProbeResult) -> bool:
    """Insert a Service candidate (status 'new') if not already present."""
    if db.execute("SELECT id FROM services WHERE canonical_domain = ?", [domain]):
        return False
    db.run(
        "INSERT INTO services (canonical_domain, name, type, models, status) "
        "VALUES (?, ?, 'other', ?, 'new')",
        [domain, p.title or domain, json_encode(p.models or None)],
    )
    return True


async def _crawl_outbound_domains(
    client: httpx.AsyncClient, domain: str, timeout: float
) -> set[str]:
    """Fetch a promoted service's pages and return outbound registrable domains.

    Reuses the already-open ``client``; fetches a handful of likely "links to
    other services" pages (homepage, /models, /providers, /docs). Every fetch
    is guarded — link-graph harvesting is best-effort and must never raise.
    """
    out: set[str] = set()
    src_reg = registrable_domain(domain) or domain
    for path in _LINKGRAPH_PATHS:
        try:
            r = await asyncio.wait_for(
                client.get(f"https://{domain}{path}"), timeout=timeout
            )
        except Exception:
            continue
        if r.status_code != 200:
            continue
        try:
            for url in extract_urls(r.text):
                reg = registrable_domain(url)
                if reg and reg != src_reg:
                    out.add(reg)
        except Exception:
            continue
    return out


async def _harvest_linkgraph(
    db,
    client: httpx.AsyncClient,
    promoted: list[str],
    timeout: float,
) -> int:
    """Crawl promoted services for novel outbound domains and queue them.

    Filters out the source domain, blocked platforms, and any domain already
    known as a service or an existing candidate. Novel domains are inserted as
    'pending' candidates with ``first_source='linkgraph'`` (INSERT OR IGNORE).
    Returns the number of domains added.
    """
    if not promoted:
        return 0
    known_services = {
        r["canonical_domain"]
        for r in db.execute("SELECT canonical_domain FROM services")
    }
    known_candidates = {
        r["domain"] for r in db.execute("SELECT domain FROM domain_candidates")
    }
    added = 0
    for src_domain in promoted:
        try:
            found = await _crawl_outbound_domains(client, src_domain, timeout)
        except Exception:
            continue
        for reg in found:
            if reg == src_domain or reg in known_services or reg in known_candidates:
                continue
            if is_blocked_domain(reg):
                continue
            try:
                db.run(
                    "INSERT OR IGNORE INTO domain_candidates "
                    "(domain, first_source, priority, status) "
                    "VALUES (?, 'linkgraph', 'normal', 'pending')",
                    [reg],
                )
            except Exception:
                continue
            known_candidates.add(reg)
            added += 1
    return added


async def run_discovery(
    limit: int = 40,
    timeout: float = 15.0,
    max_attempts: int = 3,
    budget: RunBudget | None = None,
) -> dict:
    """Probe a batch of pending candidates and promote qualifying services.

    Args:
        limit: max candidates to fetch (historical cap).
        timeout: per-probe HTTP timeout (seconds).
        max_attempts: give up on a candidate after this many failed probes.
        budget: optional :class:`RunBudget`. When given:

            * the candidate batch is capped to ``min(limit, budget.max_probes)``
              so serverless runs never queue more probes than allowed;
            * if ``budget.max_seconds`` is set, the worker stops *dequeuing*
              new probes once the wall-clock elapsed time exceeds it (probes
              already in flight are allowed to finish).

            When ``budget is None`` behaviour is identical to before.
    """
    stats = {"probed": 0, "promoted": 0, "rejected": 0, "skipped": 0,
             "linkgraph_added": 0}

    # Budget shrinks the fetch window (smaller of limit / max_probes) and arms
    # the optional wall-clock soft cap. Without a budget nothing changes.
    fetch_limit = limit
    if budget is not None:
        fetch_limit = min(limit, budget.max_probes)
    start = time.monotonic()

    def _time_exceeded() -> bool:
        return (
            budget is not None
            and budget.max_seconds is not None
            and (time.monotonic() - start) >= budget.max_seconds
        )

    with get_db() as db:
        rows = db.execute(
            # Fetch attempts/probed_at for backoff logic; priority for fast-lane ordering.
            # High-priority rows (offer trigger close to domain mention) come first.
            "SELECT id, domain, attempts, probed_at, priority "
            "FROM domain_candidates "
            "WHERE status = 'pending' AND attempts < ? "
            "ORDER BY CASE WHEN priority='high' THEN 0 ELSE 1 END, first_seen ASC "
            "LIMIT ?",
            [max_attempts, fetch_limit],
        )
        if not rows:
            log.info("discovery: no pending candidates")
            return stats

        now = _dt_str(utcnow())
        sem = asyncio.Semaphore(8)
        # Domains promoted this run — seeds for link-graph expansion below.
        promoted_domains: list[str] = []

        def _close(cid: int, status: str, summary: Optional[str] = None) -> None:
            db.run(
                "UPDATE domain_candidates SET status=?, probed_at=?, "
                "probe_result=COALESCE(?, probe_result), attempts = attempts + 1 "
                "WHERE id=?",
                [status, now, summary, cid],
            )

        async def _probe_one(client: httpx.AsyncClient, row: dict) -> None:
            cid, domain = row["id"], row["domain"]

            # Soft wall-clock cap: once exceeded, stop starting NEW probes.
            # In-flight probes (already past this point) finish normally.
            if _time_exceeded():
                stats["skipped"] += 1
                return

            # Exponential back-off: skip if this domain failed recently and
            # the minimum wait period hasn't elapsed yet.
            if _should_skip_retry(row.get("attempts", 0), row.get("probed_at")):
                stats["skipped"] += 1
                return

            reg = registrable_domain(domain) or domain

            if is_blocked_domain(reg) or not _safe_to_probe(reg):
                _close(cid, "rejected")
                stats["skipped"] += 1
                return
            if db.execute("SELECT id FROM services WHERE canonical_domain = ?", [reg]):
                _close(cid, "known")
                stats["skipped"] += 1
                return

            async with sem:
                try:
                    p = await asyncio.wait_for(probe(reg, client), timeout=timeout * 3)
                except Exception:
                    # transient failure: bump attempts, leave 'pending' for retry
                    db.run(
                        "UPDATE domain_candidates SET attempts = attempts + 1, "
                        "probed_at=? WHERE id=?",
                        [now, cid],
                    )
                    return

            stats["probed"] += 1
            summary = _summary(p)
            if should_promote(p):
                created = _promote(db, reg, p)
                _close(cid, "promoted", summary)
                if created:
                    stats["promoted"] += 1
                    promoted_domains.append(reg)
                    log.info("discovery promoted %s (models=%s amount=%s)",
                             reg, p.models, p.amount)
            else:
                _close(cid, "rejected", summary)
                stats["rejected"] += 1

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 AiApiRadar/0.1"},
        ) as client:
            await asyncio.gather(*(_probe_one(client, r) for r in rows))

            # Link-graph expansion: crawl the services we just promoted for
            # outbound AI domains and queue the novel ones. Best-effort and
            # capped — never blocks promotion or fails the run. Skipped when the
            # wall-clock budget is already spent.
            if promoted_domains and not _time_exceeded():
                cap = _LINKGRAPH_MAX_CRAWLS
                if budget is not None:
                    cap = min(cap, budget.max_probes)
                try:
                    stats["linkgraph_added"] = await _harvest_linkgraph(
                        db, client, promoted_domains[:cap], timeout
                    )
                except Exception:
                    log.debug("link-graph harvesting failed", exc_info=False)

        db.commit()

    log.info("discovery: %s", stats)
    return stats

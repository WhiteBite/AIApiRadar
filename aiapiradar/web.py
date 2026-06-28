"""FastAPI app: JSON API + minimal server-rendered dashboard.

Endpoints
  GET /                     dashboard (feed + filters)
  GET /services/{id}        service detail page
  GET /api/offers           filtered, score-sorted offers (JSON)
  GET /api/services/{id}    service + offers + recent signals (JSON)
  GET /api/stats            aggregate counts (JSON)

Data access uses the platform-agnostic Database protocol (raw SQL + `?`
placeholders), so the same code serves both SQLite (VDS) and Cloudflare D1 —
no SQLAlchemy ORM here.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .collector_meta import COLLECTOR_META as _COLLECTOR_META
from .db import get_db
from .db.base import Database, json_decode
from .util.dtutil import parse_naive as _dt_parse, to_iso as _iso
from . import sources as sources_mod

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


# Shared SELECT: every offer row carries its parent service's fields too, so a
# single row maps directly to the serialized offer dict via offer_to_dict().
_OFFER_SELECT = """
SELECT
    o.id                AS id,
    o.service_id        AS service_id,
    o.type              AS type,
    o.amount            AS amount,
    o.currency          AS currency,
    o.models            AS models,
    o.claim_steps       AS claim_steps,
    o.requirements      AS requirements,
    o.referral_required AS referral_required,
    o.effort            AS effort,
    o.unit              AS unit,
    o.description       AS description,
    o.url               AS url,
    o.score             AS score,
    o.status            AS offer_status,
    o.first_seen_at     AS first_seen_at,
    s.canonical_domain  AS canonical_domain,
    s.name              AS service_name,
    s.status            AS service_status,
    s.reliability       AS reliability,
    s.engine            AS engine,
    s.domain_first_seen AS domain_first_seen
FROM offers o
JOIN services s ON o.service_id = s.id
"""


# --- datetime helpers ------------------------------------------------------


# --- request bodies --------------------------------------------------------
class SourceCreate(BaseModel):
    type: str                              # "telegram" | "rss" | "collector"
    channel: Optional[str] = None          # telegram: @channel or channel
    topic_id: Optional[int] = None         # telegram: forum topic id
    name: Optional[str] = None             # non-telegram display name
    config: Optional[dict] = None
    enabled: bool = True


class SourceUpdate(BaseModel):
    enabled: Optional[bool] = None
    config: Optional[dict] = None
    name: Optional[str] = None


class CollectorUpdate(BaseModel):
    enabled: Optional[bool] = None
    interval: Optional[int] = None


# --- serialization ---------------------------------------------------------
def offer_to_dict(row: dict) -> dict:
    """Map a joined offer+service row (dict) to the public offer shape."""
    service_status = row.get("service_status")
    return {
        "id": row["id"],
        "service_id": row["service_id"],
        "domain": row.get("canonical_domain"),
        "name": row.get("service_name") or row.get("url"),
        "type": row.get("type"),
        "amount": row.get("amount"),
        "currency": row.get("currency"),
        "models": json_decode(row.get("models")) or [],
        "claim_steps": row.get("claim_steps"),
        "requirements": row.get("requirements"),
        "referral_required": bool(row.get("referral_required")),
        "effort": row.get("effort"),
        "unit": row.get("unit"),
        "description": row.get("description"),
        "url": row.get("url"),
        "score": round(row.get("score") or 0.0, 4),
        "status": service_status if service_status is not None else row.get("offer_status"),
        "reliability": row.get("reliability"),
        "engine": row.get("engine"),
        "domain_first_seen": _iso(row.get("domain_first_seen")),
        "first_seen_at": _iso(row.get("first_seen_at")),
    }


def query_offers(
    db: Database,
    *,
    type: Optional[str] = None,
    effort: Optional[str] = None,
    min_amount: Optional[float] = None,
    model: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    sort: Optional[str] = None,
    since_hours: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    where: list[str] = []
    params: list = []
    if type:
        where.append("o.type = ?"); params.append(type)
    if effort:
        where.append("o.effort = ?"); params.append(effort)
    if min_amount is not None:
        where.append("o.amount >= ?"); params.append(min_amount)
    if status:
        where.append("s.status = ?"); params.append(status)
    if since_hours:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=float(since_hours))
        cutoff = cutoff.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S.%f")
        where.append("o.first_seen_at >= ?"); params.append(cutoff)
    if q:
        like = f"%{q.lower()}%"
        where.append(
            "(LOWER(s.canonical_domain) LIKE ? "
            "OR LOWER(COALESCE(s.name, '')) LIKE ? "
            "OR LOWER(COALESCE(o.claim_steps, '')) LIKE ?)"
        )
        params.extend([like, like, like])

    if sort == "new":
        order = "ORDER BY o.first_seen_at DESC, o.score DESC"
    elif sort == "amount":
        # `o.amount IS NULL` sorts 0 (non-null) before 1 (null) → NULLs last.
        order = "ORDER BY o.amount IS NULL, o.amount DESC, o.score DESC"
    else:
        order = "ORDER BY o.score DESC, o.first_seen_at DESC"

    sql = _OFFER_SELECT
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " " + order

    rows = db.execute(sql, params)
    items = [offer_to_dict(r) for r in rows]

    # Attach the primary (earliest) source per offer in one extra query.
    offer_ids = [it["id"] for it in items]
    if offer_ids:
        placeholders = ", ".join(["?"] * len(offer_ids))
        src_rows = db.execute(
            f"SELECT offer_id, source, source_url FROM signals "
            f"WHERE offer_id IN ({placeholders}) ORDER BY observed_at ASC",
            offer_ids,
        )
        src_map: dict[int, dict] = {}
        for r in src_rows:
            oid = r["offer_id"]
            if oid not in src_map:
                src_map[oid] = {"source": r["source"], "source_url": r["source_url"]}
        for it in items:
            meta = src_map.get(it["id"], {})
            it["source"] = meta.get("source")
            it["source_url"] = meta.get("source_url")

    if model:  # JSON membership: simplest to post-filter
        m = model.lower()
        items = [it for it in items if any(m in str(x).lower() for x in it["models"])]
    return items[offset: offset + limit]


def compute_stats(db: Database) -> dict:
    services = db.execute("SELECT COUNT(*) AS c FROM services")[0]["c"] or 0
    offers = db.execute("SELECT COUNT(*) AS c FROM offers")[0]["c"] or 0
    active = db.execute(
        "SELECT COUNT(*) AS c FROM services WHERE status = ?", ["active"]
    )[0]["c"] or 0
    dead = db.execute(
        "SELECT COUNT(*) AS c FROM services WHERE status = ?", ["dead"]
    )[0]["c"] or 0
    by_type = {
        r["type"]: r["c"]
        for r in db.execute("SELECT type, COUNT(*) AS c FROM offers GROUP BY type")
    }
    by_effort = {
        r["effort"]: r["c"]
        for r in db.execute(
            "SELECT effort, COUNT(*) AS c FROM offers "
            "WHERE effort IS NOT NULL GROUP BY effort"
        )
    }
    return {
        "services": services,
        "offers": offers,
        "active": active,
        "dead": dead,
        "by_type": by_type,
        "by_effort": by_effort,
    }


def _parse_channel(source: str, source_url: Optional[str]) -> Optional[str]:
    """Extract a human channel/origin label from a signal."""
    if source_url and "t.me/" in source_url:
        tail = source_url.split("t.me/", 1)[1].split("/")[0]
        return f"@{tail}" if tail and not tail.startswith("+") else "Telegram"
    return None


def signal_to_dict(sig: dict) -> dict:
    """Serialize a signal row with its original text for provenance display."""
    return {
        "source": sig.get("source"),
        "source_url": sig.get("source_url"),
        "channel": _parse_channel(sig.get("source"), sig.get("source_url")),
        "raw_text": (sig.get("raw_text") or "")[:1200],
        "observed_at": _iso(sig.get("observed_at")),
    }


def create_app() -> FastAPI:
    app = FastAPI(title="AiApiRadar", version="0.1.0")

    # Allow Next.js dev server (port 3000) and any localhost origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000",
                       "http://localhost:3001", "http://127.0.0.1:3001"],
        allow_credentials=True,
        allow_methods=["GET", "PATCH"],
        allow_headers=["*"],
    )

    @app.get("/api/offers")
    def api_offers(
        type: Optional[str] = None,
        effort: Optional[str] = None,
        min_amount: Optional[float] = None,
        model: Optional[str] = None,
        status: Optional[str] = None,
        q: Optional[str] = None,
        sort: Optional[str] = None,
        since_hours: Optional[float] = None,
        limit: int = Query(100, le=500),
        offset: int = 0,
    ):
        with get_db() as db:
            items = query_offers(db, type=type, effort=effort, min_amount=min_amount, model=model,
                                 status=status, q=q, sort=sort, since_hours=since_hours,
                                 limit=limit, offset=offset)
        return {"count": len(items), "items": items}

    @app.get("/api/services/{service_id}")
    def api_service(service_id: int):
        with get_db() as db:
            svc_rows = db.execute("SELECT * FROM services WHERE id = ?", [service_id])
            if not svc_rows:
                raise HTTPException(404, "service not found")
            svc = svc_rows[0]
            offer_rows = db.execute(
                _OFFER_SELECT + " WHERE o.service_id = ?", [service_id]
            )
            offers = [offer_to_dict(r) for r in offer_rows]
            signals = db.execute(
                "SELECT * FROM signals WHERE service_id = ? "
                "ORDER BY observed_at DESC LIMIT 20",
                [service_id],
            )
            return {
                "id": svc["id"],
                "domain": svc["canonical_domain"],
                "name": svc["name"],
                "type": svc["type"],
                "engine": svc["engine"],
                "status": svc["status"],
                "reliability": svc["reliability"],
                "aliases": json_decode(svc["aliases"]) or [],
                "domain_first_seen": _iso(svc["domain_first_seen"]),
                "offers": offers,
                "signals": [signal_to_dict(sig) for sig in signals],
            }

    @app.get("/api/models")
    def api_models(include_dead: bool = False):
        """Models ranked by how many live services currently offer them."""
        with get_db() as db:
            rows = db.execute(
                "SELECT o.models AS models, s.status AS status "
                "FROM offers o JOIN services s ON o.service_id = s.id"
            )
        counts: dict[str, int] = {}
        for r in rows:
            if not include_dead and r["status"] == "dead":
                continue
            for m in (json_decode(r["models"]) or []):
                key = str(m).lower()
                counts[key] = counts.get(key, 0) + 1
        items = sorted(
            ({"model": k, "count": v} for k, v in counts.items()),
            key=lambda x: -x["count"],
        )
        return {"items": items}

    @app.get("/api/stats")
    def api_stats():
        with get_db() as db:
            return compute_stats(db)

    @app.get("/api/collectors")
    def api_collectors():
        import os
        from .collectors import get_registry, load_builtin
        from .sched.source_config import sync_sources, get_source_config
        load_builtin()
        registry = get_registry()
        with get_db() as db:  # noqa: F841 — ensures DB is live before sync
            sync_sources(registry)  # ensure rows exist
        out = []
        for name, cls in sorted(registry.items()):
            cfg = get_source_config(name)
            meta = _COLLECTOR_META.get(name, {})
            requires = meta.get("requires")
            key_present = bool(os.environ.get(requires, "").strip()) if requires else None
            out.append({
                "name": name,
                "label": meta.get("label", name),
                "dot": meta.get("dot", "zinc"),
                "kind": getattr(cls, "kind", "generic"),
                "mode": getattr(cls, "mode", "poll"),
                "interval": cfg.get("interval") or getattr(cls, "interval", 900),
                "enabled": cfg.get("enabled", True),
                "requires": requires,
                "key_present": key_present,
            })
        return out

    @app.patch("/api/collectors/{name}")
    def api_patch_collector(name: str, body: CollectorUpdate):
        import os  # noqa: F401
        from .collectors import get_registry, load_builtin
        load_builtin()
        registry = get_registry()
        if name not in registry:
            raise HTTPException(404, "collector not found")
        with get_db() as db:
            rows = db.execute("SELECT id FROM sources WHERE name = ?", [name])
            if rows:
                sets, params = [], []
                if body.enabled is not None:
                    sets.append("enabled=?"); params.append(int(body.enabled))
                if body.interval is not None:
                    # store interval in config JSON
                    existing = db.execute("SELECT config FROM sources WHERE name=?", [name])
                    from .db.base import json_decode as _jd, json_encode as _je
                    cfg = _jd((existing[0]["config"] if existing else None)) or {}
                    cfg["interval"] = body.interval
                    sets.append("config=?"); params.append(_je(cfg))
                if sets:
                    params.append(name)
                    db.run(f"UPDATE sources SET {', '.join(sets)} WHERE name=?", params)
            db.commit()
        return {"ok": True}

    @app.get("/api/keys")
    def api_keys_status():
        import os
        from .collectors import get_registry, load_builtin
        load_builtin()
        registry = get_registry()
        key_map: dict[str, list[str]] = {}
        for name in registry:
            req = _COLLECTOR_META.get(name, {}).get("requires")
            if req:
                key_map.setdefault(req, []).append(name)
        result = []
        for key, collectors in sorted(key_map.items()):
            result.append({
                "key": key,
                "present": bool(os.environ.get(key, "").strip()),
                "unlocks": collectors,
            })
        return result

    @app.get("/api/analytics")
    def api_analytics():
        with get_db() as db:
            # lead_time from lead_metrics table
            lm_rows = db.execute(
                "SELECT lead_hours FROM lead_metrics WHERE lead_hours IS NOT NULL"
            )
            hours = [r["lead_hours"] for r in lm_rows if r["lead_hours"] is not None]
            avg_h = round(sum(hours) / len(hours), 2) if hours else None
            median_h = None
            if hours:
                s = sorted(hours)
                mid = len(s) // 2
                median_h = round((s[mid - 1] + s[mid]) / 2 if len(s) % 2 == 0 else s[mid], 2)
            count_ahead = sum(1 for h in hours if h > 0)

            # by_source: signals grouped by source, sorted descending by count
            src_rows = db.execute(
                "SELECT source, COUNT(*) AS c FROM signals GROUP BY source ORDER BY c DESC"
            )
            by_source = [{"source": r["source"], "count": r["c"]} for r in src_rows]

            # with_description / offers_total
            with_desc = db.execute(
                "SELECT COUNT(*) AS c FROM offers WHERE description IS NOT NULL AND description != ''"
            )[0]["c"] or 0
            total = db.execute("SELECT COUNT(*) AS c FROM offers")[0]["c"] or 0

            return {
                "lead_time": {
                    "avg_hours": avg_h,
                    "median_hours": median_h,
                    "count_ahead": count_ahead,
                    "count_total": len(hours),
                },
                "by_source": by_source,
                "with_description": with_desc,
                "offers_total": total,
            }

    # ── Sources management (the "привязать" feature) ────────────────────────

    @app.get("/api/sources")
    def api_list_sources(type: Optional[str] = None):
        return {"items": sources_mod.list_sources(type)}

    @app.post("/api/sources")
    def api_create_source(body: SourceCreate):
        # For telegram: build a stable unique name from channel(+topic).
        if body.type == "telegram":
            ch = (body.channel or "").lstrip("@").strip()
            if not ch:
                raise HTTPException(400, "channel is required for telegram sources")
            config = {"channel": ch}
            if body.topic_id is not None:
                config["topic_id"] = body.topic_id
            name = f"@{ch}" + (f"#{body.topic_id}" if body.topic_id else "")
        else:
            config = body.config or {}
            name = body.name or body.type
        sid = sources_mod.create_source(body.type, name, config, body.enabled)
        return sources_mod.get_source(sid)

    @app.patch("/api/sources/{source_id}")
    def api_update_source(source_id: int, body: SourceUpdate):
        ok = sources_mod.update_source(
            source_id, enabled=body.enabled, config=body.config, name=body.name
        )
        if not ok:
            raise HTTPException(400, "nothing to update")
        return sources_mod.get_source(source_id)

    @app.delete("/api/sources/{source_id}")
    def api_delete_source(source_id: int):
        sources_mod.delete_source(source_id)
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    def dashboard(
        request: Request,
        type: Optional[str] = None,
        min_amount: Optional[float] = None,
        model: Optional[str] = None,
        status: Optional[str] = None,
        q: Optional[str] = None,
    ):
        with get_db() as db:
            items = query_offers(db, type=type, min_amount=min_amount, model=model,
                                 status=status, q=q, limit=200)
            stats = compute_stats(db)
        return TEMPLATES.TemplateResponse(request, "index.html", {
            "offers": items, "stats": stats,
            "filters": {"type": type or "", "min_amount": min_amount or "",
                        "model": model or "", "status": status or "", "q": q or ""},
        })

    @app.get("/services/{service_id}", response_class=HTMLResponse)
    def service_page(request: Request, service_id: int):
        with get_db() as db:
            svc_rows = db.execute("SELECT * FROM services WHERE id = ?", [service_id])
            if not svc_rows:
                raise HTTPException(404, "service not found")
            svc = svc_rows[0]
            offer_rows = db.execute(
                _OFFER_SELECT + " WHERE o.service_id = ?", [service_id]
            )
            offers = [offer_to_dict(r) for r in offer_rows]
            signal_rows = db.execute(
                "SELECT * FROM signals WHERE service_id = ? "
                "ORDER BY observed_at DESC LIMIT 20",
                [service_id],
            )
            # Templates call `.date()` / `.strftime(...)` → pass real datetimes.
            svc_ctx = {
                "canonical_domain": svc["canonical_domain"],
                "name": svc["name"],
                "type": svc["type"],
                "engine": svc["engine"],
                "status": svc["status"],
                "reliability": svc["reliability"],
                "domain_first_seen": _dt_parse(svc["domain_first_seen"]),
            }
            ctx_signals = [
                {"source": r["source"], "source_url": r["source_url"],
                 "observed_at": _dt_parse(r["observed_at"])}
                for r in signal_rows
            ]
        return TEMPLATES.TemplateResponse(request, "service.html", {
            "svc": svc_ctx, "offers": offers, "signals": ctx_signals,
        })

    return app


app = create_app()

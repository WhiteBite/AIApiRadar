"""FastAPI app: JSON API + minimal server-rendered dashboard.

Endpoints
  GET /                     dashboard (feed + filters)
  GET /services/{id}        service detail page
  GET /api/offers           filtered, score-sorted offers (JSON)
  GET /api/services/{id}    service + offers + recent signals (JSON)
  GET /api/stats            aggregate counts (JSON)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import func, select

from .db import session_scope
from .models import Offer, Service, Signal
from . import sources as sources_mod

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


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


# --- serialization ---------------------------------------------------------
def offer_to_dict(offer: Offer, service: Optional[Service]) -> dict:
    return {
        "id": offer.id,
        "service_id": offer.service_id,
        "domain": service.canonical_domain if service else None,
        "name": (service.name if service else None) or offer.url,
        "type": offer.type,
        "amount": offer.amount,
        "currency": offer.currency,
        "models": offer.models or [],
        "claim_steps": offer.claim_steps,
        "requirements": offer.requirements,
        "referral_required": offer.referral_required,
        "effort": offer.effort,
        "unit": offer.unit,
        "url": offer.url,
        "score": round(offer.score or 0.0, 4),
        "status": service.status if service else offer.status,
        "reliability": service.reliability if service else None,
        "engine": service.engine if service else None,
        "domain_first_seen": service.domain_first_seen.isoformat() if service and service.domain_first_seen else None,
        "first_seen_at": offer.first_seen_at.isoformat() if offer.first_seen_at else None,
    }


def query_offers(
    session,
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
    stmt = select(Offer, Service).join(Service, Offer.service_id == Service.id)
    if type:
        stmt = stmt.where(Offer.type == type)
    if effort:
        stmt = stmt.where(Offer.effort == effort)
    if min_amount is not None:
        stmt = stmt.where(Offer.amount >= min_amount)
    if status:
        stmt = stmt.where(Service.status == status)
    if since_hours:
        import datetime as _dt
        from .models import utcnow
        cutoff = utcnow() - _dt.timedelta(hours=float(since_hours))
        stmt = stmt.where(Offer.first_seen_at >= cutoff)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(Service.canonical_domain).like(like)
            | func.lower(func.coalesce(Service.name, "")).like(like)
            | func.lower(func.coalesce(Offer.claim_steps, "")).like(like)
        )
    if sort == "new":
        stmt = stmt.order_by(Offer.first_seen_at.desc(), Offer.score.desc())
    elif sort == "amount":
        stmt = stmt.order_by(Offer.amount.desc().nullslast(), Offer.score.desc())
    else:
        stmt = stmt.order_by(Offer.score.desc(), Offer.first_seen_at.desc())
    rows = session.execute(stmt).all()
    items = [offer_to_dict(o, s) for (o, s) in rows]

    # Attach the primary (earliest) source per offer in one extra query.
    offer_ids = [it["id"] for it in items]
    if offer_ids:
        src_rows = session.execute(
            select(Signal.offer_id, Signal.source, Signal.source_url)
            .where(Signal.offer_id.in_(offer_ids))
            .order_by(Signal.observed_at.asc())
        ).all()
        src_map: dict[int, dict] = {}
        for oid, src, surl in src_rows:
            if oid not in src_map:
                src_map[oid] = {"source": src, "source_url": surl}
        for it in items:
            meta = src_map.get(it["id"], {})
            it["source"] = meta.get("source")
            it["source_url"] = meta.get("source_url")

    if model:  # JSON membership: simplest to post-filter
        m = model.lower()
        items = [it for it in items if any(m in str(x).lower() for x in it["models"])]
    return items[offset: offset + limit]


def compute_stats(session) -> dict:
    services = session.scalar(select(func.count(Service.id))) or 0
    offers = session.scalar(select(func.count(Offer.id))) or 0
    active = session.scalar(select(func.count(Service.id)).where(Service.status == "active")) or 0
    dead = session.scalar(select(func.count(Service.id)).where(Service.status == "dead")) or 0
    by_type = dict(session.execute(select(Offer.type, func.count(Offer.id)).group_by(Offer.type)).all())
    by_effort = dict(session.execute(
        select(Offer.effort, func.count(Offer.id))
        .where(Offer.effort.isnot(None))
        .group_by(Offer.effort)
    ).all())
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


def signal_to_dict(sig: Signal) -> dict:
    """Serialize a signal with its original text for provenance display."""
    return {
        "source": sig.source,
        "source_url": sig.source_url,
        "channel": _parse_channel(sig.source, sig.source_url),
        "raw_text": (sig.raw_text or "")[:1200],
        "observed_at": sig.observed_at.isoformat() if sig.observed_at else None,
    }


def create_app() -> FastAPI:
    app = FastAPI(title="AiApiRadar", version="0.1.0")

    # Allow Next.js dev server (port 3000) and any localhost origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000",
                       "http://localhost:3001", "http://127.0.0.1:3001"],
        allow_credentials=True,
        allow_methods=["GET"],
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
        with session_scope() as s:
            items = query_offers(s, type=type, effort=effort, min_amount=min_amount, model=model,
                                 status=status, q=q, sort=sort, since_hours=since_hours,
                                 limit=limit, offset=offset)
        return {"count": len(items), "items": items}

    @app.get("/api/services/{service_id}")
    def api_service(service_id: int):
        with session_scope() as s:
            svc = s.get(Service, service_id)
            if not svc:
                raise HTTPException(404, "service not found")
            offers = [offer_to_dict(o, svc) for o in
                      s.scalars(select(Offer).where(Offer.service_id == service_id)).all()]
            signals = s.scalars(
                select(Signal).where(Signal.service_id == service_id)
                .order_by(Signal.observed_at.desc()).limit(20)
            ).all()
            return {
                "id": svc.id,
                "domain": svc.canonical_domain,
                "name": svc.name,
                "type": svc.type,
                "engine": svc.engine,
                "status": svc.status,
                "reliability": svc.reliability,
                "aliases": svc.aliases or [],
                "domain_first_seen": svc.domain_first_seen.isoformat() if svc.domain_first_seen else None,
                "offers": offers,
                "signals": [signal_to_dict(sig) for sig in signals],
            }

    @app.get("/api/models")
    def api_models(include_dead: bool = False):
        """Models ranked by how many live services currently offer them."""
        with session_scope() as s:
            stmt = select(Offer.models, Service.status).join(
                Service, Offer.service_id == Service.id
            )
            counts: dict[str, int] = {}
            for models, status in s.execute(stmt).all():
                if not include_dead and status == "dead":
                    continue
                for m in (models or []):
                    key = str(m).lower()
                    counts[key] = counts.get(key, 0) + 1
        items = sorted(
            ({"model": k, "count": v} for k, v in counts.items()),
            key=lambda x: -x["count"],
        )
        return {"items": items}

    @app.get("/api/stats")
    def api_stats():
        with session_scope() as s:
            return compute_stats(s)

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
        with session_scope() as s:
            items = query_offers(s, type=type, min_amount=min_amount, model=model,
                                 status=status, q=q, limit=200)
            stats = compute_stats(s)
        return TEMPLATES.TemplateResponse(request, "index.html", {
            "offers": items, "stats": stats,
            "filters": {"type": type or "", "min_amount": min_amount or "",
                        "model": model or "", "status": status or "", "q": q or ""},
        })

    @app.get("/services/{service_id}", response_class=HTMLResponse)
    def service_page(request: Request, service_id: int):
        with session_scope() as s:
            svc = s.get(Service, service_id)
            if not svc:
                raise HTTPException(404, "service not found")
            offers = [offer_to_dict(o, svc) for o in
                      s.scalars(select(Offer).where(Offer.service_id == service_id)).all()]
            signals = s.scalars(
                select(Signal).where(Signal.service_id == service_id)
                .order_by(Signal.observed_at.desc()).limit(20)
            ).all()
            ctx_signals = [
                {"source": sig.source, "source_url": sig.source_url,
                 "observed_at": sig.observed_at} for sig in signals
            ]
        return TEMPLATES.TemplateResponse(request, "service.html", {
            "svc": svc, "offers": offers, "signals": ctx_signals,
        })

    return app


app = create_app()

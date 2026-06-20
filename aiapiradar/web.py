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
from sqlalchemy import func, select

from .db import session_scope
from .models import Offer, Service, Signal

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


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
    min_amount: Optional[float] = None,
    model: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    stmt = select(Offer, Service).join(Service, Offer.service_id == Service.id)
    if type:
        stmt = stmt.where(Offer.type == type)
    if min_amount is not None:
        stmt = stmt.where(Offer.amount >= min_amount)
    if status:
        stmt = stmt.where(Service.status == status)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(Service.canonical_domain).like(like)
            | func.lower(func.coalesce(Service.name, "")).like(like)
            | func.lower(func.coalesce(Offer.claim_steps, "")).like(like)
        )
    stmt = stmt.order_by(Offer.score.desc(), Offer.first_seen_at.desc())
    rows = session.execute(stmt).all()
    items = [offer_to_dict(o, s) for (o, s) in rows]
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
    return {
        "services": services,
        "offers": offers,
        "active": active,
        "dead": dead,
        "by_type": by_type,
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
        min_amount: Optional[float] = None,
        model: Optional[str] = None,
        status: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = Query(100, le=500),
        offset: int = 0,
    ):
        with session_scope() as s:
            items = query_offers(s, type=type, min_amount=min_amount, model=model,
                                 status=status, q=q, limit=limit, offset=offset)
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
                "domain_first_seen": svc.domain_first_seen.isoformat() if svc.domain_first_seen else None,
                "offers": offers,
                "signals": [
                    {"source": sig.source, "source_url": sig.source_url,
                     "observed_at": sig.observed_at.isoformat() if sig.observed_at else None}
                    for sig in signals
                ],
            }

    @app.get("/api/stats")
    def api_stats():
        with session_scope() as s:
            return compute_stats(s)

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

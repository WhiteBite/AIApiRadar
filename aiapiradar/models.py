"""SQLAlchemy ORM models — the core data model.

Relationship:  Service  <--  Offer  <--  Signal
A single deal (Offer) belongs to one canonical Service and is backed by many
Signals (independent observations from different sources).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


# --- Offer / service classification vocab ----------------------------------
OFFER_TYPES = (
    "relay",          # Chinese-style API relay / 中转站
    "saas_trial",     # legit SaaS free credits / trial
    "saas_promo",     # promo on an established SaaS (referral/coupon/edu cohort)
    "model_release",  # new model release (HF/GitHub)
    "grant",          # credits for GitHub star / action
    "abuse",          # edu/financial abuse method, no public source
    "other",
)

STATUSES = ("new", "active", "dead", "unknown")


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_domain: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(32), default="other")
    engine: Mapped[Optional[str]] = mapped_column(String(64))  # new-api/one-api/sub2api/...
    models: Mapped[Optional[list]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="new")
    reliability: Mapped[float] = mapped_column(Float, default=0.0)
    domain_first_seen: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    first_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_checked: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))

    offers: Mapped[list["Offer"]] = relationship(back_populates="service")


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True)
    type: Mapped[str] = mapped_column(String(32), default="other")
    amount: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[Optional[str]] = mapped_column(String(8))
    models: Mapped[Optional[list]] = mapped_column(JSON)
    claim_steps: Mapped[Optional[str]] = mapped_column(Text)
    requirements: Mapped[Optional[str]] = mapped_column(Text)
    referral_required: Mapped[bool] = mapped_column(Boolean, default=False)
    url: Mapped[Optional[str]] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(16), default="new")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_verified_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    notified_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))

    service: Mapped["Service"] = relationship(back_populates="offers")
    signals: Mapped[list["Signal"]] = relationship(back_populates="offer")


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("source", "source_url", name="uq_signal_source_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("offers.id"), index=True)
    service_id: Mapped[Optional[int]] = mapped_column(ForeignKey("services.id"), index=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1024))
    url: Mapped[Optional[str]] = mapped_column(String(1024))
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    lang: Mapped[Optional[str]] = mapped_column(String(8))
    classification: Mapped[Optional[dict]] = mapped_column(JSON)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    offer: Mapped[Optional["Offer"]] = relationship(back_populates="signals")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    config: Mapped[Optional[dict]] = mapped_column(JSON)


class LeadMetric(Base):
    __tablename__ = "lead_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"), unique=True, index=True)
    first_seen_by_us: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    first_seen_in_aggregator: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    lead_hours: Mapped[Optional[float]] = mapped_column(Float)

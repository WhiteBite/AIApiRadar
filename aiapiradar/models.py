"""Core domain constants (data model lives in db/schema.sql + SCHEMA_SQL).

The SQLAlchemy ORM that used to live here was removed: both production targets
(Cloudflare D1 over REST, and SQLite on VPS) talk to the DB through the raw-SQL
``Database`` protocol (aiapiradar/db), and tests use the same path via
tests/factories.py. Only these vocabulary/constant helpers remain.
"""
from __future__ import annotations

import datetime as dt


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


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

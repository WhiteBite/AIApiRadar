"""Enrichment / resolution for Service rows.

Probes a service to answer: is it alive? does it have a /pricing page with
offer triggers? what relay engine powers it? how old is the domain (crt.sh)?
These feed the reliability score used by the scorer and watchdog.

This package was split out of the former single-file ``enrich.py``. Every
public name is re-exported here so ``from aiapiradar.enrich import X`` keeps
working unchanged:

  - probe / orchestration      -> .probe
  - model & engine detection   -> .detect
  - offer-path & relay sweep   -> .offer_paths
  - robots/sitemap discovery   -> .sitemap
  - HTML text extraction       -> .text
"""
from __future__ import annotations

from .detect import (
    ENGINE_BODY_MARKS,
    ENGINE_TITLE_EXACT,
    _AMOUNT_CREDIT_RE,
    _AMOUNT_USD_RE,
    _EXACT_RES,
    _EXACT_TOKENS,
    _SUBSTR_TOKENS,
    detect_amount,
    detect_engine,
    detect_models,
)
from .offer_paths import (
    MAX_PROBE_REQUESTS,
    OFFER_PATHS,
    PRICING_TRIGGERS,
    RELAY_MODELS_PATH,
    RELAY_NOTICE_PATH,
    RELAY_STATUS_PATH,
    _RELAY_RESERVE,
    _probe_relay_endpoints,
    _ReqBudget,
)
from .probe import (
    ProbeResult,
    crtsh_earliest,
    earliest_not_before,
    enrich_service,
    probe,
    reliability_score,
    _enrich_service_db,
)
from .sitemap import _OFFER_URL_RE, _SITEMAP_LOC_RE, _discover_offer_urls
from .text import (
    _clean_text,
    _make_description,
    _meta_description,
    _title,
    _visible_text,
)

__all__ = [
    # probe / orchestration
    "probe",
    "ProbeResult",
    "crtsh_earliest",
    "earliest_not_before",
    "reliability_score",
    "enrich_service",
    # detection
    "detect_models",
    "detect_amount",
    "detect_engine",
    # offer paths / relay
    "OFFER_PATHS",
    "MAX_PROBE_REQUESTS",
    "PRICING_TRIGGERS",
    "RELAY_STATUS_PATH",
    "RELAY_MODELS_PATH",
    "RELAY_NOTICE_PATH",
    # text helpers
    "_make_description",
]

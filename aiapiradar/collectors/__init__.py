"""Collector registry.

Collectors register themselves here so the scheduler can discover them without
hard-coded imports. Phase 2+ collectors call `register()` at import time.
"""
from __future__ import annotations

from typing import Dict, Type

from ..core.collector import Collector

_REGISTRY: Dict[str, Type[Collector]] = {}


def register(cls: Type[Collector]) -> Type[Collector]:
    """Class decorator to register a collector implementation."""
    if not getattr(cls, "name", None) or cls.name == "base":
        raise ValueError(f"Collector {cls!r} must define a unique 'name'")
    if cls.name in _REGISTRY:
        raise ValueError(f"Duplicate collector name: {cls.name}")
    _REGISTRY[cls.name] = cls
    return cls


def get_registry() -> Dict[str, Type[Collector]]:
    return dict(_REGISTRY)


def load_builtin() -> None:
    """Import built-in collector modules so they self-register."""
    from . import (  # noqa: F401
        certstream, crtsh, coupon, directories, fofa, forum_rss, github,
        github_lists, hackernews, huggingface, leaks, openrouter, packages,
        producthunt, reddit, searchdorks, telegram, twitter, youtube,
    )

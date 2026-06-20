"""Collector base class. Every source is a plugin implementing this interface.

A collector knows ONLY how to fetch from its source and emit Signals. It never
touches the database, classifier, or scoring — that keeps the core decoupled
and makes adding a source a single-file change.
"""
from __future__ import annotations

import abc
from typing import Iterable

from .signal import Signal


class Collector(abc.ABC):
    #: unique short name, stored on each emitted Signal
    name: str = "base"
    #: collector category (informational / scheduling hints)
    kind: str = "generic"
    #: default polling interval in seconds (realtime collectors may ignore)
    interval: int = 900

    @abc.abstractmethod
    async def collect(self) -> Iterable[Signal]:
        """Fetch from the source and return an iterable of Signals.

        Implementations MUST NOT raise on transient network errors when
        avoidable — log and return what was gathered.
        """
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<Collector {self.name} kind={self.kind} interval={self.interval}s>"

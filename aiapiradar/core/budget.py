"""Run budget — cap outbound work on resource-limited (serverless) platforms.

Background
----------
On a VDS the app runs as a long-lived process with no hard ceiling on outbound
HTTP work, so it can probe as many candidates as it likes. Serverless cron
platforms (Cloudflare Workers) are different: a single invocation has hard caps
on the number of outbound subrequests it may make and on CPU/wall-clock time.
Blowing past either limit kills the whole run.

``RunBudget`` captures those caps in one place so the discovery worker and the
batch runner can stay within them. On a VDS the budget is effectively
unbounded (``max_subrequests=None``); on Cloudflare it is built from
``Settings`` (``max_subrequests`` / ``discovery_limit``).

The object is intentionally tiny and dependency-free so it can be threaded
through async code without ceremony.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RunBudget:
    """Caps for one run's outbound work.

    Attributes:
        max_subrequests: total outbound subrequests allowed this run.
            ``None`` means unlimited (the VDS default).
        max_seconds: soft wall-clock cap in seconds. ``None`` = no time cap.
            It is a *soft* cap: callers check it between units of work, so any
            in-flight request is allowed to finish.
        max_probes: how many discovery domains may be probed this run. Defaults
            to 40 to match the historical discovery batch size.
    """

    max_subrequests: int | None = None   # None = unlimited (VDS)
    max_seconds: float | None = None     # wall-clock soft cap
    max_probes: int = 40                 # discovery domains per run

    # Internal counter of subrequests consumed so far this run. Not part of the
    # public constructor contract; tracked via ``allow()``.
    _used: int = field(default=0, init=False, repr=False)

    @classmethod
    def from_settings(cls) -> "RunBudget":
        """Build a budget from the application ``Settings``.

        ``max_subrequests = settings.max_subrequests or None`` (0 → None, i.e.
        the VDS "unlimited" sentinel becomes a real ``None``).
        ``max_probes = settings.discovery_limit``.
        ``max_seconds`` is left unset (no global wall-clock cap by default).
        """
        from ..config import get_settings

        settings = get_settings()
        return cls(
            max_subrequests=settings.max_subrequests or None,
            max_probes=settings.discovery_limit,
        )

    def allow(self, n: int = 1) -> bool:
        """Reserve ``n`` subrequests, returning whether they fit the budget.

        When ``max_subrequests`` is ``None`` (unlimited) this always returns
        ``True`` and still tracks usage for reporting. Otherwise it returns
        ``True`` and consumes the quota only if ``n`` more subrequests stay
        within the cap; if they would exceed it, nothing is consumed and it
        returns ``False``.
        """
        if self.max_subrequests is None:
            self._used += n
            return True
        if self._used + n > self.max_subrequests:
            return False
        self._used += n
        return True

    @property
    def used(self) -> int:
        """Subrequests consumed so far this run (via ``allow``)."""
        return self._used

    @property
    def remaining(self) -> int | None:
        """Subrequests still available, or ``None`` when unlimited."""
        if self.max_subrequests is None:
            return None
        return max(0, self.max_subrequests - self._used)

"""CertStream collector — realtime Certificate Transparency monitor.

Why: a brand-new relay/SaaS gets a TLS cert the moment its domain goes live,
which appears in public CT logs *hours before* any forum/Telegram post. We
proved this on freemodel.dev (cert 13 days before the chat post).

Design: a shared background websocket thread buffers matching domains; the
scheduler drains the buffer every `interval` seconds via collect(). State is
class-level because the scheduler instantiates a fresh collector per run.

Two harvest paths:
  1. Keyword buffer (_buffer): domain contains an AI/relay keyword → Signal
     with force_classify=True so the pipeline classifies it immediately.
  2. TLD harvest buffer (_harvest_buffer): domain has an always-harvest TLD
     (.ai/.io/.app/.dev) but no keyword match → Signal with service_candidate=True
     but WITHOUT force_classify. The probe worker (discover.py) decides if it's
     a real AI service. This catches brandable names like "zenmux.ai" that have
     no AI keywords in the hostname.
"""
from __future__ import annotations

import json
import threading
from collections import deque
from typing import Iterable

from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("certstream")

# Substrings that suggest an AI API relay / gateway / model service.
DOMAIN_KEYWORDS = (
    "router", "-api", "api-", "gateway", "relay", "llm", "gpt", "claude",
    "gemini", "aiproxy", "proxy", "oneapi", "one-api", "newapi", "new-api",
    "token", "freemodel", "chatapi", "aihub", "aigc", "openai", "anthropic",
    "deepseek", "qwen", "glm", "aiapi", "modelapi",
)

# Obvious false positives to drop.
_DENY = ("apigee", "gateway.fb", "googleapis", "api.telegram")

# TLDs where ~90% of new domains ARE AI/tech products.
# Every new domain on these TLDs goes straight into the discovery queue so the
# probe worker can assess it, regardless of whether its name contains a keyword.
# Zone rationale:
#   .ai/.io/.app/.dev   — the established AI/dev startup zones (original set).
#   .so/.run/.cloud     — increasingly used by infra/SaaS and deploy platforms.
#   .bot/.chat          — almost exclusively conversational-AI / agent products.
#   .tools/.build/.tech — common for developer tooling and API/platform launches.
# .co/.space are deliberately kept OUT for now: too noisy (generic registrations).
ALWAYS_HARVEST_TLDS = (".ai", ".io", ".app", ".dev", ".so", ".run",
                       ".cloud", ".bot", ".chat", ".tools", ".build", ".tech")

# Subdomain prefixes that strongly hint "this is an API / commerce product",
# even when the registrable domain name carries no AI keyword. A cert whose SAN
# list contains e.g. api.foobar.com / console.foobar.com / billing.foobar.com is
# almost always a developer platform worth probing.
SUBDOMAIN_SIGNALS = ("api.", "console.", "dashboard.", "studio.",
                     "playground.", "billing.", "developer.", "developers.")


def domain_matches(domain: str) -> bool:
    """Return True if the domain name contains an AI/relay keyword."""
    d = domain.lower().lstrip("*.")
    if any(bad in d for bad in _DENY):
        return False
    return any(k in d for k in DOMAIN_KEYWORDS)


def _has_always_harvest_tld(domain: str) -> bool:
    """Return True if the registrable domain ends with one of ALWAYS_HARVEST_TLDS."""
    d = domain.lower().lstrip("*.")
    return any(d.endswith(tld) for tld in ALWAYS_HARVEST_TLDS)


def _has_subdomain_signal(domain: str) -> bool:
    """Return True if the host's first label is a known API/commerce signal."""
    d = domain.lower().lstrip("*.")
    return any(d.startswith(sig) for sig in SUBDOMAIN_SIGNALS)


def _strip_subdomain_signal(domain: str) -> str:
    """Strip a leading signal label (api./console./...) to the registrable domain.

    e.g. "api.foobar.com" -> "foobar.com". Only strips when the first label is a
    known signal prefix; otherwise returns the cleaned domain unchanged.
    """
    d = domain.lower().lstrip("*.")
    if _has_subdomain_signal(d) and "." in d:
        return d.split(".", 1)[1]
    return d


@register
class CertStreamCollector(Collector):
    name = "certstream"
    kind = "ct-stream"
    interval = 60
    # Long-lived websocket thread + class-level in-memory buffers must persist
    # between collect() calls, so this collector can only run on a VDS.
    mode = "stream"
    URL = "wss://certstream.calidog.io/"

    # shared across instances (scheduler builds a new instance per run)
    _buffer: "deque[str]" = deque(maxlen=10000)
    # Separate buffer for TLD-based harvest (no keyword required).
    _harvest_buffer: "deque[str]" = deque(maxlen=50000)
    _seen: set[str] = set()
    _thread: threading.Thread | None = None
    _lock = threading.Lock()

    @classmethod
    def _on_message(cls, message: str) -> None:
        try:
            data = json.loads(message)
        except Exception:
            return
        if data.get("message_type") != "certificate_update":
            return
        domains = (data.get("data", {}).get("leaf_cert", {}) or {}).get("all_domains", []) or []
        with cls._lock:
            for dom in domains:
                clean = dom.lstrip("*.")
                if domain_matches(dom):
                    # Keyword match: strong signal, classify immediately.
                    if clean in cls._seen:
                        continue
                    cls._seen.add(clean)
                    cls._buffer.append(clean)
                elif _has_always_harvest_tld(dom) or _has_subdomain_signal(dom):
                    # TLD-only OR subdomain-signal harvest: brandable name /
                    # developer platform, probe worker decides. Harvest the
                    # registrable domain (strip leading api./console./... label)
                    # so the probe targets the real service, and dedup on it.
                    target = _strip_subdomain_signal(dom)
                    if target in cls._seen:
                        continue
                    cls._seen.add(target)
                    cls._harvest_buffer.append(target)

    @classmethod
    def _run_ws(cls) -> None:  # pragma: no cover - network loop
        import websocket  # websocket-client

        while True:
            try:
                ws = websocket.WebSocketApp(
                    cls.URL,
                    on_message=lambda _ws, msg: cls._on_message(msg),
                )
                ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception:
                log.exception("certstream socket dropped; reconnecting")
            import time
            time.sleep(5)

    @classmethod
    def ensure_started(cls) -> None:  # pragma: no cover - network
        with cls._lock:
            if cls._thread is None or not cls._thread.is_alive():
                cls._thread = threading.Thread(target=cls._run_ws, daemon=True, name="certstream-ws")
                cls._thread.start()
                log.info("certstream websocket thread started")

    async def collect(self) -> Iterable[Signal]:
        self.ensure_started()
        out: list[Signal] = []

        with self._lock:
            # Path 1: keyword-matched domains → classify immediately.
            while self._buffer:
                dom = self._buffer.popleft()
                out.append(Signal(
                    source=self.name,
                    raw_text=dom,
                    url=f"https://{dom}",
                    source_url=f"certstream://{dom}",
                    meta={"service_candidate": True, "force_classify": True},
                ))

            # Path 2: TLD-harvest domains → probe worker decides, no classify.
            harvest_count = 0
            while self._harvest_buffer:
                dom = self._harvest_buffer.popleft()
                out.append(Signal(
                    source=self.name,
                    raw_text=dom,
                    url=f"https://{dom}",
                    source_url=f"certstream://{dom}",
                    meta={"service_candidate": True},
                ))
                harvest_count += 1

        if out:
            keyword_count = len(out) - harvest_count
            log.info(
                "certstream drained %d keyword + %d TLD-harvest candidate domains",
                keyword_count, harvest_count,
            )
        return out

"""CertStream collector — realtime Certificate Transparency monitor.

Why: a brand-new relay/SaaS gets a TLS cert the moment its domain goes live,
which appears in public CT logs *hours before* any forum/Telegram post. We
proved this on freemodel.dev (cert 13 days before the chat post).

Design: a shared background websocket thread buffers matching domains; the
scheduler drains the buffer every `interval` seconds via collect(). State is
class-level because the scheduler instantiates a fresh collector per run.
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


def domain_matches(domain: str) -> bool:
    d = domain.lower().lstrip("*.")
    if any(bad in d for bad in _DENY):
        return False
    return any(k in d for k in DOMAIN_KEYWORDS)


@register
class CertStreamCollector(Collector):
    name = "certstream"
    kind = "ct-stream"
    interval = 60
    URL = "wss://certstream.calidog.io/"

    # shared across instances (scheduler builds a new instance per run)
    _buffer: "deque[str]" = deque(maxlen=10000)
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
                if domain_matches(dom) and dom not in cls._seen:
                    cls._seen.add(dom)
                    cls._buffer.append(dom.lstrip("*."))

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
            while self._buffer:
                dom = self._buffer.popleft()
                out.append(Signal(
                    source=self.name,
                    raw_text=dom,
                    url=f"https://{dom}",
                    source_url=f"certstream://{dom}",
                    meta={"service_candidate": True, "force_classify": True},
                ))
        if out:
            log.info("certstream drained %d candidate domains", len(out))
        return out

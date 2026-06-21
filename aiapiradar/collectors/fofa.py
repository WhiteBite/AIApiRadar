"""FOFA collector — relay panels by favicon hash (§8.1). KEY-GATED.

Relay engines (new-api / one-api and forks) ship a recognisable favicon. FOFA
indexes hosts by the mmh3 hash of their base64-encoded favicon, so a single
`icon_hash="<hash>"` query surfaces every public panel running that engine —
including brand-new relay stations that haven't been posted anywhere yet.

Requires AIRADAR_FOFA_KEY (+ AIRADAR_FOFA_EMAIL). Without them the collector is
not configured: collect() returns [] with a one-time INFO log (never an error).
FOFA free quotas are tiny, so every request path is guarded.

Emitted Signals carry meta={"service_candidate": True} and NO force_classify —
the probe worker decides whether a host is a live relay.
"""
from __future__ import annotations

import base64
from typing import Iterable

import httpx

from ..config import get_settings
from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("fofa")

API = "https://fofa.info/api/v1/search/all"

# Known relay-engine favicon mmh3 hashes (new-api / one-api family).
# These are PLACEHOLDERS — operators should replace them with real hashes.
# How to compute one: download the panel's /favicon.ico, base64-encode the
# raw bytes (including a trailing newline, as FOFA does), then mmh3.hash() the
# resulting string. The signed 32-bit int is the value FOFA expects.
RELAY_FAVICON_HASHES: list[int] = [
    0,          # placeholder — replace with a real new-api favicon mmh3 hash
    1,          # placeholder — replace with a real one-api favicon mmh3 hash
]


def favicon_mmh3(raw: bytes) -> int:
    """Compute the FOFA-style mmh3 hash of a raw favicon.

    mmh3 is an optional dependency — imported lazily so module import (and
    therefore load_builtin) never fails when it is absent. We ship static
    hashes in RELAY_FAVICON_HASHES, so live hashing is not required at runtime.
    """
    import mmh3  # lazy import; optional dependency

    b64 = base64.encodebytes(raw)  # FOFA encodes with line breaks + trailing \n
    return mmh3.hash(b64)


def parse_fofa(data: dict) -> list[Signal]:
    """Pure parse: FOFA `search/all` response -> Signals. No network.

    FOFA returns `{results: [[host, ...], ...]}` where the first column is the
    host (per the default `fields=host` projection).
    """
    out: list[Signal] = []
    for row in (data or {}).get("results", []):
        host = row[0] if isinstance(row, (list, tuple)) and row else (row if isinstance(row, str) else "")
        host = (host or "").strip()
        if not host:
            continue
        # FOFA hosts may already include a scheme; normalise to a bare host.
        host = host.replace("https://", "").replace("http://", "").strip("/")
        if not host:
            continue
        out.append(Signal(
            source="fofa",
            raw_text=f"Possible relay panel: {host}",
            url=f"https://{host}",
            source_url=f"https://{host}",
            meta={"service_candidate": True, "host": host},
        ))
    return out


@register
class FofaCollector(Collector):
    name = "fofa"
    kind = "api"
    interval = 21600  # 6h — quotas are tiny

    def __init__(self, hashes: list[int] | None = None, timeout: float = 25.0):
        self.hashes = hashes if hashes is not None else RELAY_FAVICON_HASHES
        self.timeout = timeout
        self._warned = False  # emit the not-configured info log once per process

    def _creds(self) -> tuple[str, str]:
        s = get_settings()
        return (
            getattr(s, "fofa_key", "") or "",
            getattr(s, "fofa_email", "") or "",
        )

    def configured(self) -> bool:
        key, _email = self._creds()
        return bool(key)

    async def collect(self) -> Iterable[Signal]:
        if not self.configured():
            if not self._warned:
                log.info(
                    "fofa disabled (no AIRADAR_FOFA_KEY). Set AIRADAR_FOFA_KEY "
                    "(+ AIRADAR_FOFA_EMAIL) to enable favicon-hash relay discovery."
                )
                self._warned = True
            return []

        key, email = self._creds()
        out: list[Signal] = []
        headers = {"User-Agent": "AiApiRadar/0.1"}
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            for h in self.hashes:
                try:
                    query = f'icon_hash="{h}"'
                    qbase64 = base64.b64encode(query.encode("utf-8")).decode("ascii")
                    r = await client.get(API, params={
                        "email": email,
                        "key": key,
                        "qbase64": qbase64,
                        "fields": "host",
                        "size": 100,
                    })
                    if r.status_code == 200:
                        data = r.json()
                        if data.get("error"):
                            log.warning("fofa api error: %s", data.get("errmsg"))
                            break  # quota / auth error — stop hitting the API
                        out.extend(parse_fofa(data))
                    else:
                        log.warning("fofa search -> %s", r.status_code)
                except Exception:
                    log.warning("fofa search failed", exc_info=False)
        log.info("fofa collected %d hosts", len(out))
        return out

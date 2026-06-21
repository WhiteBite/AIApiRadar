"""Telegram ingest — the 'tail' source.

Abuse-scene methods (edu hacks, promo codes) have no public source; they only
surface inside the Telegram channel graph. We tap the upstream channels
directly. Source name is 'telegram' so these count as AGGREGATOR_SOURCES for
lead-time metrics (i.e. they should usually be LATER than our own discovery).

Telethon runs in a dedicated thread with its own event loop (like certstream),
buffering messages that collect() drains. Degrades to no-op without creds.
First run requires interactive login to create the session file.
"""
from __future__ import annotations

import datetime as dt
import threading
from collections import deque
from typing import Iterable, Optional

from ..config import get_settings
from ..core.collector import Collector
from ..core.signal import Signal
from ..logging_conf import get_logger
from . import register

log = get_logger("telegram")

# Upstream channels identified from the real export analysis.
CHANNELS = [
    "asati_shill", "aipappi", "kyloai", "vibecoderchat", "D3vin_dev",
    "ikhdev1", "IknewsChat", "aiclew", "valencylab",
]

# Upstream channels surfaced via forward-chain harvest (§4.7). These are the
# source channels our monitored aggregators forward FROM. We never auto-subscribe
# (manual review required) — we just surface them for an operator to add.
_lock_upstream = threading.Lock()
_DISCOVERED_UPSTREAM: set[str] = set()


def extract_forward_from(message) -> Optional[str]:  # noqa: ANN001
    """Pure: pull the upstream channel identity from a message's forward origin.

    Works defensively via getattr so it never raises on unexpected shapes and
    returns None when a message wasn't forwarded. Prefers a @username, then the
    channel title, then the raw forwarded-from name.
    """
    fwd = getattr(message, "forward", None)
    if fwd is not None:
        chat = getattr(fwd, "chat", None)
        username = getattr(chat, "username", None)
        if username:
            return username
        title = getattr(chat, "title", None)
        if title:
            return title
        from_name = getattr(fwd, "from_name", None)
        if from_name:
            return from_name
    # Fallback to the raw header (telethon MessageFwdHeader).
    hdr = getattr(message, "fwd_from", None)
    if hdr is not None:
        from_name = getattr(hdr, "from_name", None)
        if from_name:
            return from_name
    return None


def record_upstream(username: Optional[str]) -> None:
    """Surface a discovered upstream channel for operator review (no auto-subscribe)."""
    if not username:
        return
    with _lock_upstream:
        if username not in _DISCOVERED_UPSTREAM:
            _DISCOVERED_UPSTREAM.add(username)
            log.info("discovered upstream channels: %s", sorted(_DISCOVERED_UPSTREAM))


def discovered_upstream() -> list[str]:
    """Snapshot of upstream channels harvested from forward chains this process."""
    with _lock_upstream:
        return sorted(_DISCOVERED_UPSTREAM)


def build_signal(text: str, channel: str, msg_id: int,
                 date: Optional[dt.datetime] = None,
                 forward_from: Optional[str] = None) -> Signal:
    meta = {"channel": channel}
    if forward_from:
        meta["forward_from"] = forward_from
    return Signal(
        source="telegram",
        raw_text=(text or "")[:8000],
        source_url=f"https://t.me/{channel}/{msg_id}",
        observed_at=date or dt.datetime.now(dt.timezone.utc),
        meta=meta,
    )


@register
class TelegramCollector(Collector):
    name = "telegram"
    kind = "ingest"
    interval = 120
    # Persistent background thread + deque buffer — VDS-only, same as CertStreamCollector.
    # batch_runner must skip it (counts as collectors_skipped_stream, not a poll target).
    mode = "stream"
    CHANNELS = CHANNELS

    _buffer: "deque[Signal]" = deque(maxlen=5000)
    _thread: threading.Thread | None = None
    _lock = threading.Lock()

    @classmethod
    def _load_config(cls) -> tuple[list[str], dict[str, int]]:
        """Load enabled channels + topic filters from the DB sources table.

        Falls back to the hardcoded CHANNELS list if none configured yet.
        Returns (channel_list, {channel: topic_id}).
        """
        try:
            from ..sources import enabled_telegram_channels
            configured = enabled_telegram_channels()
        except Exception:
            log.warning("could not load telegram sources from DB", exc_info=False)
            configured = []
        if not configured:
            return list(cls.CHANNELS), {}
        channels = [c["channel"] for c in configured]
        topics = {c["channel"]: c["topic_id"] for c in configured if c.get("topic_id")}
        return channels, topics

    @staticmethod
    def configured() -> bool:
        s = get_settings()
        return bool(s.tg_api_id and s.tg_api_hash)

    @classmethod
    def _run_client(cls) -> None:  # pragma: no cover - network/loop
        import asyncio

        from telethon import TelegramClient, events

        s = get_settings()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = TelegramClient(s.tg_session, s.tg_api_id, s.tg_api_hash, loop=loop)

        channels, topics = cls._load_config()

        def _topic_ok(event, channel: str) -> bool:
            """If a topic_id is configured for this channel, keep only that topic."""
            want = topics.get(channel)
            if not want:
                return True
            reply = getattr(event.message, "reply_to", None)
            tid = getattr(reply, "reply_to_top_id", None) or getattr(reply, "reply_to_msg_id", None)
            return tid == want

        @client.on(events.NewMessage(chats=channels))
        async def _handler(event):  # noqa: ANN001
            chat = await event.get_chat()
            channel = getattr(chat, "username", None) or str(event.chat_id)
            if not _topic_ok(event, channel):
                return
            forward_from = extract_forward_from(event.message)
            record_upstream(forward_from)
            sig = build_signal(event.message.message, channel, event.message.id,
                               event.message.date, forward_from=forward_from)
            with cls._lock:
                cls._buffer.append(sig)

        try:
            client.start()
            log.info("telegram client started; listening on %d channels", len(channels))
            client.run_until_disconnected()
        except Exception:
            log.exception("telegram client error")

    @classmethod
    def ensure_started(cls) -> None:  # pragma: no cover - network
        with cls._lock:
            if cls._thread is None or not cls._thread.is_alive():
                cls._thread = threading.Thread(target=cls._run_client, daemon=True,
                                               name="telegram-ingest")
                cls._thread.start()

    async def collect(self) -> Iterable[Signal]:
        if not self.configured():
            log.info("telegram ingest disabled (no api_id/api_hash)")
            return []
        self.ensure_started()
        out: list[Signal] = []
        with self._lock:
            while self._buffer:
                out.append(self._buffer.popleft())
        if out:
            log.info("telegram drained %d messages", len(out))
        return out

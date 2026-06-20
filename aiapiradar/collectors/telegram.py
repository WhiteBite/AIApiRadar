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


def build_signal(text: str, channel: str, msg_id: int,
                 date: Optional[dt.datetime] = None) -> Signal:
    return Signal(
        source="telegram",
        raw_text=(text or "")[:8000],
        source_url=f"https://t.me/{channel}/{msg_id}",
        observed_at=date or dt.datetime.now(dt.timezone.utc),
        meta={"channel": channel},
    )


@register
class TelegramCollector(Collector):
    name = "telegram"
    kind = "ingest"
    interval = 120
    CHANNELS = CHANNELS

    _buffer: "deque[Signal]" = deque(maxlen=5000)
    _thread: threading.Thread | None = None
    _lock = threading.Lock()

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

        @client.on(events.NewMessage(chats=cls.CHANNELS))
        async def _handler(event):  # noqa: ANN001
            chat = await event.get_chat()
            channel = getattr(chat, "username", None) or str(event.chat_id)
            sig = build_signal(event.message.message, channel, event.message.id,
                               event.message.date)
            with cls._lock:
                cls._buffer.append(sig)

        try:
            client.start()
            log.info("telegram client started; listening on %d channels", len(cls.CHANNELS))
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

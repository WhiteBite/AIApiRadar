"""Telegram Bot API plumbing for the notifier package."""
from __future__ import annotations

from typing import Optional

import httpx

from ..logging_conf import get_logger

log = get_logger("notifier")


# ── Telegram Bot API plumbing ──────────────────────────────────────────────
async def _tg_request(method: str, payload: dict, client: httpx.AsyncClient,
                      token: str) -> tuple[bool, dict]:
    """Call one Bot API method. Returns (ok, result_dict).

    Tolerant of mock transports that return `{"ok": true}` without a `result`.
    """
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        r = await client.post(url, json=payload)
    except Exception:
        log.warning("telegram %s error", method, exc_info=False)
        return False, {}
    try:
        data = r.json()
    except Exception:
        data = {}
    ok = r.status_code == 200 and bool(data.get("ok", True))
    if not ok:
        log.warning("telegram %s failed: status=%s body=%s", method, r.status_code, data)
    return ok, (data.get("result") or {})


async def send_telegram(text: str, client: httpx.AsyncClient, token: str, chat_id: str) -> bool:
    """Legacy single-chat send (kept for backward compatibility)."""
    ok, _ = await _tg_request("sendMessage", {
        "chat_id": chat_id, "text": text, "disable_web_page_preview": True,
    }, client, token)
    return ok


async def send_to_topic(text: str, client: httpx.AsyncClient, token: str,
                        chat_id: str, thread_id: Optional[int]) -> bool:
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if thread_id:
        payload["message_thread_id"] = int(thread_id)
    ok, _ = await _tg_request("sendMessage", payload, client, token)
    return ok


async def create_forum_topic(name: str, chat_id: str, client: httpx.AsyncClient,
                             token: str, icon_color: Optional[int] = None) -> Optional[int]:
    payload: dict = {"chat_id": chat_id, "name": name}
    if icon_color:
        payload["icon_color"] = icon_color
    ok, result = await _tg_request("createForumTopic", payload, client, token)
    tid = result.get("message_thread_id")
    if ok and tid:
        return int(tid)
    return None

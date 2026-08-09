"""Thin Telegram Bot API client."""

from __future__ import annotations

import html
import logging

import httpx

from config import TELEGRAM_API, require_bot_token

log = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def esc(text: str) -> str:
    """Escape user text for parse_mode=HTML."""
    return html.escape(text or "", quote=False)


async def send_message(
    chat_id: int,
    text: str,
    *,
    reply_to: int | None = None,
    preview: bool = False,
) -> None:
    require_bot_token()
    payload: dict[str, object] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": not preview},
    }
    if reply_to is not None:
        payload["reply_parameters"] = {
            "message_id": reply_to,
            "allow_sending_without_reply": True,
        }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(f"{TELEGRAM_API}/sendMessage", json=payload)
        if response.status_code != 200:
            log.error("sendMessage failed %s: %s", response.status_code, response.text)
    except httpx.HTTPError:
        # A failed confirmation must never crash the handler — the expense is
        # already saved, and Telegram would retry the whole update.
        log.exception("sendMessage transport error")


async def get_me() -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.get(f"{TELEGRAM_API}/getMe")
    return response.json()

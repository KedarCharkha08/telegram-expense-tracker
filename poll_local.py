"""Run the bot locally with long polling — no deploy, no public URL.

    python poll_local.py

Use this to test end-to-end from your phone before touching Render. Telegram
allows either a webhook or getUpdates, never both, so this script deletes any
registered webhook on start (re-register later with set_webhook.py).

Ctrl-C to stop.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from config import TELEGRAM_API, require_bot_token
from handlers import handle_update

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("poller")

LONG_POLL_SECONDS = 25


async def main() -> None:
    require_bot_token()

    async with httpx.AsyncClient(timeout=LONG_POLL_SECONDS + 10) as client:
        me = (await client.get(f"{TELEGRAM_API}/getMe")).json()
        if not me.get("ok"):
            raise SystemExit(f"Bad bot token: {me}")
        log.info("polling as @%s — message it from Telegram", me["result"]["username"])

        # getUpdates and webhooks are mutually exclusive.
        await client.post(f"{TELEGRAM_API}/deleteWebhook")

        offset: int | None = None
        while True:
            params: dict[str, object] = {
                "timeout": LONG_POLL_SECONDS,
                "allowed_updates": '["message"]',
            }
            if offset is not None:
                params["offset"] = offset

            try:
                response = await client.get(f"{TELEGRAM_API}/getUpdates", params=params)
                payload = response.json()
            except httpx.HTTPError as exc:
                log.warning("poll failed (%s), retrying in 3s", exc)
                await asyncio.sleep(3)
                continue

            if not payload.get("ok"):
                log.error("getUpdates error: %s", payload)
                await asyncio.sleep(3)
                continue

            for update in payload.get("result", []):
                offset = update["update_id"] + 1
                await handle_update(update)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("stopped")

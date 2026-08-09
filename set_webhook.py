"""Register, inspect, or remove the Telegram webhook.

    python set_webhook.py https://your-app.onrender.com   # register
    python set_webhook.py --info                          # show current state
    python set_webhook.py --delete                        # back to polling
"""

from __future__ import annotations

import json
import sys

import httpx

from config import TELEGRAM_API, WEBHOOK_SECRET, require_bot_token

PATH = "/api/telegram-webhook"


def main(argv: list[str]) -> int:
    require_bot_token()

    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__)
        return 0

    if argv[0] == "--info":
        show(httpx.get(f"{TELEGRAM_API}/getWebhookInfo").json())
        return 0

    if argv[0] == "--delete":
        show(httpx.post(f"{TELEGRAM_API}/deleteWebhook").json())
        return 0

    base = argv[0].rstrip("/")
    if not base.startswith("https://"):
        print("Telegram requires an https URL.")
        return 1
    if not WEBHOOK_SECRET:
        print("Refusing to register without TELEGRAM_WEBHOOK_SECRET set in .env.")
        return 1

    response = httpx.post(
        f"{TELEGRAM_API}/setWebhook",
        json={
            "url": base + PATH,
            "secret_token": WEBHOOK_SECRET,
            "allowed_updates": ["message"],
            "drop_pending_updates": True,
            "max_connections": 10,
        },
    )
    show(response.json())
    print(f"\nWebhook target: {base + PATH}")
    return 0


def show(payload: dict) -> None:
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""Environment configuration, loaded once."""

from __future__ import annotations

import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Asia/Kolkata"))
CURRENCY_SYMBOL = {"INR": "₹", "USD": "$", "EUR": "€"}.get(
    os.getenv("CURRENCY", "INR").upper(), "₹"
)


def allowed_user_ids() -> set[int]:
    """Telegram user IDs permitted to write. Empty set = nobody (locked)."""
    raw = os.getenv("ALLOWED_USER_IDS", "")
    return {int(part) for part in raw.replace(" ", "").split(",") if part}


def require_bot_token() -> str:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set (see .env.example)")
    return BOT_TOKEN

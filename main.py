"""FastAPI webhook receiver for the Telegram expense bot.

Design note — why the handler returns before the work is done:

Telegram treats any non-200 (or a slow response) as a failed delivery and
retries the update, with backoff, and eventually disables the webhook. On a
free tier that sleeps, the cold start alone can eat most of the budget. So the
endpoint validates the caller, hands the update to a background task, and
returns 200 immediately. Duplicate protection lives in the database
(`expenses.update_id` is UNIQUE), not in the response time.
"""

from __future__ import annotations

import logging

from fastapi import BackgroundTasks, FastAPI, Header, Request, Response

import db
from config import WEBHOOK_SECRET
from handlers import handle_update

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("expense-bot")

app = FastAPI(title="Telegram Expense Tracker", docs_url=None, redoc_url=None)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "telegram-expense-tracker", "status": "ok"}


@app.get("/healthz")
async def healthz(response: Response) -> dict[str, object]:
    ok = db.health_check()
    response.status_code = 200 if ok else 503
    return {"ok": ok, "database": "up" if ok else "down"}


@app.post("/api/telegram-webhook")
async def telegram_webhook(
    request: Request,
    background: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> Response:
    # The URL is effectively public. This header is what proves the POST
    # actually came from Telegram and not from someone spraying the endpoint.
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        log.warning("rejected webhook call with bad secret token")
        return Response(status_code=403)

    try:
        update = await request.json()
    except Exception:
        log.warning("webhook received non-JSON body")
        return Response(status_code=200)  # never make Telegram retry a bad body

    log.info("update %s received", update.get("update_id"))
    background.add_task(handle_update, update)
    return Response(status_code=200)

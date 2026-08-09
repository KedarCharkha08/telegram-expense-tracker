"""Update handling — the shared brain behind both the webhook and the
local long-polling runner.

`handle_update` is deliberately total: it logs and swallows its own errors so
that neither transport ever returns a non-200 to Telegram (which would trigger
redelivery and, eventually, a disabled webhook).
"""

from __future__ import annotations

import asyncio
import logging

import db
from bot import esc, send_message
from config import CURRENCY_SYMBOL, allowed_user_ids
from parser import ParseError, format_amount, parse_expense

log = logging.getLogger(__name__)

HELP = """<b>How to log an expense</b>

Just type the amount and a keyword:
• <code>250 food dinner</code>
• <code>dinner 250</code>
• <code>₹1,250 uber to airport</code>
• <code>1.2k rent</code>
• <code>300 lunch yesterday</code>

Order doesn't matter. Without a keyword it lands in <i>Uncategorized</i>.

<b>Commands</b>
/today — today's total
/month — this month by category
/last — last 10 expenses
/undo — remove the most recent one
/help — this message"""


async def handle_update(update: dict) -> None:
    try:
        await _dispatch(update)
    except Exception:
        log.exception("unhandled error processing update %s", update.get("update_id"))


async def _dispatch(update: dict) -> None:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    text = (message.get("text") or "").strip()
    if not text:
        return

    chat_id = message["chat"]["id"]
    user_id = (message.get("from") or {}).get("id")
    update_id = update.get("update_id")

    allowed = allowed_user_ids()
    if not allowed:
        log.warning("ALLOWED_USER_IDS is empty — refusing writes. Caller id=%s", user_id)
        await send_message(
            chat_id,
            "This bot isn't configured yet.\n\n"
            f"Your Telegram ID is <code>{user_id}</code> — add it to "
            "<code>ALLOWED_USER_IDS</code> and restart.",
        )
        return

    if user_id not in allowed:
        log.warning("rejected message from unauthorized user %s", user_id)
        await send_message(chat_id, "Sorry, this is a private bot.")
        return

    command = text.split()[0].lower().lstrip("/").split("@")[0] if text.startswith("/") else None
    if command:
        await _run_command(command, chat_id, user_id)
        return

    await _log_expense(text, chat_id, user_id, update_id, message.get("message_id"))


async def _log_expense(
    text: str,
    chat_id: int,
    user_id: int,
    update_id: int | None,
    message_id: int | None,
) -> None:
    try:
        expense = parse_expense(text, today=db.today_local())
    except ParseError:
        await send_message(
            chat_id,
            "I couldn't find an amount in that.\n\n"
            "Try something like <code>250 food dinner</code>. /help for more.",
            reply_to=message_id,
        )
        return

    try:
        await asyncio.to_thread(
            db.insert_expense,
            expense,
            tg_user_id=user_id,
            tg_chat_id=chat_id,
            update_id=update_id,
        )
    except db.DuplicateUpdate:
        log.info("ignoring redelivered update %s", update_id)
        return
    except Exception:
        log.exception("insert failed")
        await send_message(
            chat_id,
            "⚠️ Couldn't save that — the database rejected it. "
            "Nothing was logged, so try again.",
            reply_to=message_id,
        )
        return

    line = (
        f"Logged {format_amount(expense.amount, CURRENCY_SYMBOL)} "
        f"under <b>{esc(expense.category)}</b>"
    )
    if expense.description:
        line += f" — <i>{esc(expense.description)}</i>"
    if expense.spent_on != db.today_local():
        line += f"  ({expense.spent_on:%d %b})"
    if not expense.is_categorized:
        line += "\n\n<i>Tip: add a word like</i> <code>food</code> <i>or</i> <code>uber</code> <i>to categorize it.</i>"

    await send_message(chat_id, line, reply_to=message_id)


async def _run_command(command: str, chat_id: int, user_id: int) -> None:
    if command in {"start", "help"}:
        await send_message(chat_id, HELP)

    elif command == "today":
        today = db.today_local()
        total = await asyncio.to_thread(db.total_between, today, today, tg_user_id=user_id)
        await send_message(
            chat_id,
            f"<b>Today</b> ({today:%d %b})\n"
            f"Spent: {format_amount(total, CURRENCY_SYMBOL)}",
        )

    elif command == "month":
        start, end = db.month_bounds()
        totals = await asyncio.to_thread(
            db.category_totals, start, end, tg_user_id=user_id
        )
        if not totals:
            await send_message(chat_id, f"Nothing logged yet in {start:%B}.")
            return
        grand = sum(amount for _, amount in totals)
        rows = "\n".join(
            f"  {esc(category):<16} {format_amount(amount, CURRENCY_SYMBOL)}"
            for category, amount in totals
        )
        await send_message(
            chat_id,
            f"<b>{start:%B %Y}</b> — {format_amount(grand, CURRENCY_SYMBOL)}\n"
            f"<pre>{rows}</pre>",
        )

    elif command == "last":
        rows = await asyncio.to_thread(db.recent, 10, tg_user_id=user_id)
        if not rows:
            await send_message(chat_id, "No expenses yet.")
            return
        lines = []
        for row in rows:
            label = row["description"] or row["category"]
            lines.append(
                f"{row['spent_on'][5:]}  "
                f"{format_amount(float(row['amount']), CURRENCY_SYMBOL)}  "
                f"{esc(label)}"
            )
        await send_message(chat_id, "<b>Last 10</b>\n<pre>" + "\n".join(lines) + "</pre>")

    elif command == "undo":
        row = await asyncio.to_thread(db.soft_delete_last, user_id)
        if not row:
            await send_message(chat_id, "Nothing to undo.")
            return
        await send_message(
            chat_id,
            f"Removed {format_amount(float(row['amount']), CURRENCY_SYMBOL)} "
            f"from <b>{esc(row['category'])}</b>.",
        )

    else:
        await send_message(chat_id, "Unknown command. /help for the list.")

"""Supabase data access for the expense tracker.

Backend-only module: it uses the service_role key, which bypasses RLS.
Never import this from the Streamlit dashboard.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from supabase import Client, create_client

from parser import ParsedExpense

load_dotenv()
log = logging.getLogger(__name__)

TABLE = "expenses"
TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Kolkata"))


class DuplicateUpdate(Exception):
    """Telegram re-delivered an update we have already stored."""


@lru_cache(maxsize=1)
def get_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set (see .env.example)"
        )
    return create_client(url, key)


def today_local() -> date:
    return datetime.now(TZ).date()


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #

def insert_expense(
    expense: ParsedExpense,
    *,
    tg_user_id: int | None = None,
    tg_chat_id: int | None = None,
    update_id: int | None = None,
) -> dict[str, Any]:
    """Insert one expense and return the stored row.

    Raises DuplicateUpdate if this Telegram update_id was already recorded,
    which happens whenever Telegram retries a delivery it thinks failed.
    """
    payload = {
        "amount": float(expense.amount),
        "category": expense.category,
        "description": expense.description,
        "spent_on": expense.spent_on.isoformat(),
        "raw_message": expense.raw_message,
        "tg_user_id": tg_user_id,
        "tg_chat_id": tg_chat_id,
        "update_id": update_id,
    }

    try:
        response = get_client().table(TABLE).insert(payload).execute()
    except Exception as exc:  # supabase wraps PostgREST errors loosely
        if _is_unique_violation(exc):
            raise DuplicateUpdate(f"update_id {update_id} already stored") from exc
        raise

    if not response.data:
        raise RuntimeError("insert returned no rows")
    return response.data[0]


def soft_delete_last(tg_user_id: int) -> dict[str, Any] | None:
    """Mark this user's most recent live expense deleted. Powers /undo."""
    client = get_client()
    found = (
        client.table(TABLE)
        .select("id, amount, category, description")
        .eq("tg_user_id", tg_user_id)
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not found.data:
        return None

    row = found.data[0]
    client.table(TABLE).update(
        {"deleted_at": datetime.now(TZ).isoformat()}
    ).eq("id", row["id"]).execute()
    return row


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #

def _live(select: str = "*"):
    return (
        get_client()
        .table(TABLE)
        .select(select)
        .is_("deleted_at", "null")
    )


def total_between(
    start: date, end: date, *, tg_user_id: int | None = None
) -> float:
    """Sum of live expenses with spent_on in [start, end]."""
    query = _live("amount").gte("spent_on", start.isoformat()).lte(
        "spent_on", end.isoformat()
    )
    if tg_user_id is not None:
        query = query.eq("tg_user_id", tg_user_id)
    rows = query.execute().data or []
    return round(sum(float(r["amount"]) for r in rows), 2)


def category_totals(
    start: date, end: date, *, tg_user_id: int | None = None
) -> list[tuple[str, float]]:
    """[(category, total)] over the window, biggest first."""
    query = _live("category, amount").gte("spent_on", start.isoformat()).lte(
        "spent_on", end.isoformat()
    )
    if tg_user_id is not None:
        query = query.eq("tg_user_id", tg_user_id)

    totals: dict[str, float] = {}
    for row in query.execute().data or []:
        totals[row["category"]] = totals.get(row["category"], 0.0) + float(row["amount"])
    return sorted(
        ((c, round(t, 2)) for c, t in totals.items()),
        key=lambda pair: pair[1],
        reverse=True,
    )


def recent(limit: int = 10, *, tg_user_id: int | None = None) -> list[dict[str, Any]]:
    query = (
        _live("spent_on, amount, category, description")
        .order("spent_on", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if tg_user_id is not None:
        query = query.eq("tg_user_id", tg_user_id)
    return query.execute().data or []


def month_bounds(today: date | None = None) -> tuple[date, date]:
    today = today or today_local()
    start = today.replace(day=1)
    next_month = (start + timedelta(days=32)).replace(day=1)
    return start, next_month - timedelta(days=1)


def health_check() -> bool:
    """Cheap connectivity probe used by /healthz."""
    try:
        get_client().table(TABLE).select("id").limit(1).execute()
        return True
    except Exception:
        log.exception("supabase health check failed")
        return False


def _is_unique_violation(exc: Exception) -> bool:
    text = f"{getattr(exc, 'code', '')} {getattr(exc, 'message', '')} {exc}".lower()
    return "23505" in text or "duplicate key" in text

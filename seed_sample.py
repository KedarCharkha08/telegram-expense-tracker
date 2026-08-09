"""Fill the database with plausible sample expenses, for trying the dashboard.

    python seed_sample.py            # insert ~90 days of data
    python seed_sample.py --purge    # remove every sample row, leave real ones

Sample rows are tagged with SAMPLE_USER_ID, which is not a real Telegram id.
That keeps them out of the bot's /today, /month, /last and /undo (all of which
filter by the sender's id) while still showing up on the dashboard, which reads
every row. Purging is therefore exact: nothing you logged yourself is touched.
"""

from __future__ import annotations

import random
import sys
from datetime import date, datetime, timedelta

import db

SAMPLE_USER_ID = 1  # sentinel: no real Telegram account has this id
DAYS = 90
SEED = 20260809  # fixed so re-running produces the same shape

# (category, description, min, max, mean-events-per-week)
RECURRING_DAILY = [
    ("Food", ["lunch", "office lunch", "thali", "canteen"], 120, 400, 5.0),
    ("Food", ["chai", "coffee", "filter coffee"], 30, 180, 4.0),
    ("Food", ["dinner", "swiggy", "zomato order", "dinner out"], 200, 900, 3.0),
    ("Transport", ["uber to office", "ola", "auto", "rapido"], 80, 520, 3.5),
    ("Transport", ["metro", "bus"], 20, 70, 2.5),
    ("Groceries", ["vegetables", "dmart run", "milk and eggs", "zepto"], 200, 2400, 1.8),
    ("Personal", ["laundry", "salon", "haircut"], 150, 900, 0.5),
    ("Entertainment", ["movie", "drinks", "bar", "concert"], 300, 2200, 0.8),
    ("Shopping", ["amazon", "clothes", "shoes", "flipkart"], 400, 6500, 0.7),
    ("Health", ["pharmacy", "medicines", "doctor", "gym"], 200, 2600, 0.5),
    ("Education", ["books", "udemy course"], 300, 1800, 0.25),
    ("Gifts", ["gift", "donation", "temple"], 200, 3000, 0.3),
]

# (day-of-month, category, description, min, max)
MONTHLY = [
    (1, "Rent", "monthly rent", 34000, 34000),
    (2, "Home", "maid and cook", 3800, 4200),
    (3, "Investment", "sip", 15000, 15000),
    (5, "Utilities", "electricity bill", 900, 3600),
    (6, "Utilities", "internet broadband", 799, 799),
    (7, "Utilities", "mobile recharge", 299, 899),
    (8, "Entertainment", "netflix subscription", 649, 649),
    (14, "Health", "insurance premium", 1800, 2400),
]

# One-off bigger events sprinkled across the window.
OCCASIONAL = [
    ("Travel", "weekend trip hotel", 4000, 12000),
    ("Travel", "flight tickets", 5500, 14000),
    ("Shopping", "headphones", 2500, 9000),
    ("Health", "dental checkup", 1500, 4000),
    ("Food", "birthday dinner", 2500, 6000),
]


def build_rows(today: date) -> list[dict]:
    rng = random.Random(SEED)
    rows: list[dict] = []
    start = today - timedelta(days=DAYS - 1)

    for offset in range(DAYS):
        day = start + timedelta(days=offset)
        weekend = day.weekday() >= 5

        for category, notes, low, high, per_week in RECURRING_DAILY:
            chance = per_week / 7.0
            if category == "Entertainment" and weekend:
                chance *= 2.5
            if category == "Transport" and weekend:
                chance *= 0.5
            if rng.random() > chance:
                continue
            note = rng.choice(notes)
            amount = round(rng.uniform(low, high), -1 if high > 500 else 0)
            rows.append(_row(day, category, note, max(amount, 20)))

        for dom, category, note, low, high in MONTHLY:
            if day.day == dom:
                amount = round(rng.uniform(low, high), -1)
                rows.append(_row(day, category, note, amount))

    for category, note, low, high in OCCASIONAL:
        for _ in range(rng.randint(1, 3)):
            day = start + timedelta(days=rng.randrange(DAYS))
            rows.append(_row(day, category, note, round(rng.uniform(low, high), -1)))

    rows.sort(key=lambda r: r["spent_on"])
    return rows


def _row(day: date, category: str, note: str, amount: float) -> dict:
    return {
        "amount": float(amount),
        "category": category,
        "description": note,
        "spent_on": day.isoformat(),
        "raw_message": f"[sample] {amount:.0f} {note}",
        "tg_user_id": SAMPLE_USER_ID,
        "tg_chat_id": SAMPLE_USER_ID,
        "created_at": datetime.combine(
            day, datetime.min.time(), tzinfo=db.TZ
        ).isoformat(),
    }


def purge() -> int:
    client = db.get_client()
    existing = (
        client.table(db.TABLE)
        .select("id")
        .eq("tg_user_id", SAMPLE_USER_ID)
        .execute()
        .data
        or []
    )
    if existing:
        client.table(db.TABLE).delete().eq("tg_user_id", SAMPLE_USER_ID).execute()
    return len(existing)


def main(argv: list[str]) -> int:
    if "--purge" in argv:
        print(f"removed {purge()} sample rows")
        return 0

    removed = purge()  # keep re-runs idempotent
    if removed:
        print(f"cleared {removed} rows from a previous seed")

    rows = build_rows(db.today_local())
    client = db.get_client()
    for chunk in (rows[i : i + 200] for i in range(0, len(rows), 200)):
        client.table(db.TABLE).insert(chunk).execute()

    total = sum(r["amount"] for r in rows)
    print(f"inserted {len(rows)} sample expenses over {DAYS} days, ₹{total:,.0f} total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

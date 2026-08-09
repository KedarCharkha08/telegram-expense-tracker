"""End-to-end handler tests with the database and Telegram stubbed out."""

import asyncio
from datetime import date

import pytest

import db
import handlers

TODAY = date(2026, 8, 9)
ME = 42
STRANGER = 999


@pytest.fixture
def wired(monkeypatch):
    """Stub Telegram + Supabase; return the recorders."""
    sent: list[tuple[int, str]] = []
    inserted: list[dict] = []

    async def fake_send(chat_id, text, **kwargs):
        sent.append((chat_id, text))

    def fake_insert(expense, **kwargs):
        row = {"expense": expense, **kwargs}
        inserted.append(row)
        return row

    monkeypatch.setattr(handlers, "send_message", fake_send)
    monkeypatch.setattr(handlers, "allowed_user_ids", lambda: {ME})
    monkeypatch.setattr(db, "today_local", lambda: TODAY)
    monkeypatch.setattr(db, "insert_expense", fake_insert)
    return sent, inserted


def run(text, user_id=ME, update_id=1):
    update = {
        "update_id": update_id,
        "message": {
            "message_id": 7,
            "chat": {"id": user_id},
            "from": {"id": user_id},
            "text": text,
        },
    }
    asyncio.run(handlers.handle_update(update))


def test_expense_is_saved_and_confirmed(wired):
    sent, inserted = wired
    run("250 food dinner")

    assert len(inserted) == 1
    expense = inserted[0]["expense"]
    assert expense.amount == 250.0
    assert expense.category == "Food"
    assert inserted[0]["tg_user_id"] == ME
    assert inserted[0]["update_id"] == 1

    assert "Logged ₹250" in sent[0][1]
    assert "<b>Food</b>" in sent[0][1]


def test_unparseable_message_is_not_saved(wired):
    sent, inserted = wired
    run("hey there")
    assert inserted == []
    assert "couldn't find an amount" in sent[0][1]


def test_stranger_is_refused(wired):
    sent, inserted = wired
    run("250 food", user_id=STRANGER)
    assert inserted == []
    assert "private bot" in sent[0][1]


def test_empty_allowlist_locks_the_bot_and_reveals_your_id(monkeypatch, wired):
    sent, inserted = wired
    monkeypatch.setattr(handlers, "allowed_user_ids", lambda: set())
    run("250 food")
    assert inserted == []
    assert "isn't configured yet" in sent[0][1]
    assert str(ME) in sent[0][1]


def test_redelivered_update_is_silently_ignored(monkeypatch, wired):
    sent, inserted = wired

    def duplicate(expense, **kwargs):
        raise db.DuplicateUpdate("already stored")

    monkeypatch.setattr(db, "insert_expense", duplicate)
    run("250 food")
    assert inserted == []
    assert sent == []  # no second confirmation for the same expense


def test_database_failure_tells_the_user_nothing_was_saved(monkeypatch, wired):
    sent, _ = wired
    monkeypatch.setattr(db, "insert_expense", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    run("250 food")
    assert "Couldn't save" in sent[0][1]


def test_html_injection_in_description_is_escaped(wired):
    sent, _ = wired
    run("250 food <b>hack</b>")
    assert "&lt;b&gt;hack&lt;/b&gt;" in sent[0][1]


def test_help_command(wired):
    sent, inserted = wired
    run("/help")
    assert inserted == []
    assert "How to log an expense" in sent[0][1]


def test_today_command(monkeypatch, wired):
    sent, _ = wired
    monkeypatch.setattr(db, "total_between", lambda *a, **k: 1234.0)
    run("/today")
    assert "₹1,234" in sent[0][1]


def test_undo_command(monkeypatch, wired):
    sent, _ = wired
    monkeypatch.setattr(
        db, "soft_delete_last", lambda uid: {"amount": 250, "category": "Food"}
    )
    run("/undo")
    assert "Removed ₹250" in sent[0][1]


def test_undo_with_nothing_to_remove(monkeypatch, wired):
    sent, _ = wired
    monkeypatch.setattr(db, "soft_delete_last", lambda uid: None)
    run("/undo")
    assert "Nothing to undo" in sent[0][1]


def test_command_with_bot_suffix_still_works(monkeypatch, wired):
    """In groups Telegram sends /today@kedarExpensesBOT."""
    sent, _ = wired
    monkeypatch.setattr(db, "total_between", lambda *a, **k: 0.0)
    run("/today@kedarExpensesBOT")
    assert "Today" in sent[0][1]


def test_non_text_update_is_ignored(wired):
    sent, inserted = wired
    asyncio.run(handlers.handle_update({"update_id": 2, "message": {"chat": {"id": ME}}}))
    assert (sent, inserted) == ([], [])

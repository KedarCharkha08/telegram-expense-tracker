"""Webhook contract tests: auth, and never-retry-me responses."""

import main
from fastapi.testclient import TestClient

client = TestClient(main.app)

UPDATE = {
    "update_id": 1,
    "message": {
        "message_id": 5,
        "chat": {"id": 42},
        "from": {"id": 42},
        "text": "250 food dinner",
    },
}


def _post(body, secret, monkeypatch):
    seen = []
    monkeypatch.setattr(main, "WEBHOOK_SECRET", "topsecret")
    monkeypatch.setattr(
        main, "handle_update", lambda update: seen.append(update) or None
    )
    headers = {} if secret is None else {"X-Telegram-Bot-Api-Secret-Token": secret}
    return client.post("/api/telegram-webhook", json=body, headers=headers), seen


def test_rejects_missing_secret(monkeypatch):
    response, seen = _post(UPDATE, None, monkeypatch)
    assert response.status_code == 403
    assert seen == []


def test_rejects_wrong_secret(monkeypatch):
    response, seen = _post(UPDATE, "guess", monkeypatch)
    assert response.status_code == 403
    assert seen == []


def test_accepts_correct_secret(monkeypatch):
    response, seen = _post(UPDATE, "topsecret", monkeypatch)
    assert response.status_code == 200
    assert seen == [UPDATE]


def test_malformed_body_still_returns_200(monkeypatch):
    """A 500 here would make Telegram retry forever and disable the webhook."""
    monkeypatch.setattr(main, "WEBHOOK_SECRET", "topsecret")
    response = client.post(
        "/api/telegram-webhook",
        content=b"not json",
        headers={"X-Telegram-Bot-Api-Secret-Token": "topsecret"},
    )
    assert response.status_code == 200


def test_root_is_public():
    assert client.get("/").status_code == 200

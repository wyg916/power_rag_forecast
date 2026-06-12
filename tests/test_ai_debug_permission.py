from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import assistant as assistant_endpoint
from backend.app.main import app


client = TestClient(app)


def _fake_answer_chat(question, **kwargs):
    payload = {
        "session_id": "session_test",
        "answer": "ok",
        "created_at": "2026-06-08 00:00:00",
    }
    if kwargs.get("debug"):
        payload.update({"trace": {"steps": []}, "workflow": ["x"], "tool_calls": [], "intent": "general_query"})
    return payload


def test_viewer_debug_true_is_downgraded(monkeypatch):
    monkeypatch.setattr(assistant_endpoint, "answer_chat", _fake_answer_chat)
    monkeypatch.setattr(assistant_endpoint, "write_audit_log", lambda **kwargs: True)
    response = client.post(
        "/api/ai/chat",
        headers={"X-User": "viewer1", "X-Role": "viewer"},
        json={"question": "你好", "debug": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "trace" not in payload
    assert "workflow" not in payload
    assert "tool_calls" not in payload
    assert "intent" not in payload


def test_developer_debug_true_returns_debug_fields(monkeypatch):
    monkeypatch.setattr(assistant_endpoint, "answer_chat", _fake_answer_chat)
    monkeypatch.setattr(assistant_endpoint, "write_audit_log", lambda **kwargs: True)
    response = client.post(
        "/api/ai/chat",
        headers={"X-User": "dev1", "X-Role": "developer"},
        json={"question": "你好", "debug": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["trace"] == {"steps": []}
    assert payload["workflow"] == ["x"]
    assert payload["tool_calls"] == []
    assert payload["intent"] == "general_query"

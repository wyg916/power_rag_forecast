from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import assistant as assistant_endpoint
from backend.app.api.v1.endpoints import report as report_endpoint
from backend.app.auth.password import hash_password
from backend.app.core.config import reset_settings_cache
from backend.app.db.session import reset_db_cache
from backend.app.main import app
from backend.app.repositories import audit_repository, user_repository
from backend.app.repositories.audit_repository import clear_memory_audit_logs
from backend.app.repositories.user_repository import clear_memory_users, create_user


client = TestClient(app)


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("JWT_SECRET_KEY", "unit_test_jwt_secret")
    monkeypatch.setenv("DATABASE_URL", "")
    reset_settings_cache()
    reset_db_cache()
    monkeypatch.setattr(user_repository, "postgres_engine", lambda: None)
    monkeypatch.setattr(audit_repository, "postgres_engine", lambda: None)
    clear_memory_users()
    clear_memory_audit_logs()
    yield
    clear_memory_users()
    clear_memory_audit_logs()
    reset_settings_cache()
    reset_db_cache()


def _token(username: str, role: str) -> str:
    create_user(
        username=username,
        password_hash=hash_password("Password123!"),
        display_name=username,
        role=role,
        is_active=True,
    )
    response = client.post("/api/auth/login", json={"username": username, "password": "Password123!"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_viewer_cannot_generate_report():
    token = _token("viewer1", "viewer")
    response = client.post("/api/reports/generate", headers={"Authorization": f"Bearer {token}"}, json={"run_id": "latest"})
    assert response.status_code == 403


def test_analyst_can_generate_report(monkeypatch):
    token = _token("analyst1", "analyst")
    monkeypatch.setattr(
        report_endpoint,
        "enqueue_task",
        lambda kind, payload=None: {"task_id": "task_report_test", "kind": kind, "status": "pending", "payload": payload or {}},
    )
    response = client.post("/api/reports/generate", headers={"Authorization": f"Bearer {token}"}, json={"run_id": "latest"})
    assert response.status_code == 200
    assert response.json()["task_id"] == "task_report_test"


def test_admin_can_read_audit_logs():
    token = _token("admin1", "admin")
    response = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert "logs" in response.json()


def test_viewer_debug_true_is_downgraded(monkeypatch):
    token = _token("viewer2", "viewer")

    def fake_answer_chat(question, **kwargs):
        payload = {"session_id": "s1", "answer": "ok"}
        if kwargs.get("debug"):
            payload.update({"trace": {"steps": []}, "workflow": ["x"], "tool_calls": [], "intent": "general_query"})
        return payload

    monkeypatch.setattr(assistant_endpoint, "answer_chat", fake_answer_chat)
    response = client.post(
        "/api/ai/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "你好", "debug": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "trace" not in payload
    assert "workflow" not in payload
    assert "tool_calls" not in payload
    assert "intent" not in payload


def test_developer_debug_true_returns_debug_fields(monkeypatch):
    token = _token("dev1", "developer")

    def fake_answer_chat(question, **kwargs):
        payload = {"session_id": "s1", "answer": "ok"}
        if kwargs.get("debug"):
            payload.update({"trace": {"steps": []}, "workflow": ["x"], "tool_calls": [], "intent": "general_query"})
        return payload

    monkeypatch.setattr(assistant_endpoint, "answer_chat", fake_answer_chat)
    response = client.post(
        "/api/ai/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "你好", "debug": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["trace"] == {"steps": []}
    assert payload["workflow"] == ["x"]
    assert payload["tool_calls"] == []
    assert payload["intent"] == "general_query"

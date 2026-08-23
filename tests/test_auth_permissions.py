from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import report as report_endpoint
from backend.app.core.security import CurrentUser, ROLE_PERMISSIONS, get_current_user
from backend.app.main import app


client = TestClient(app)


def test_viewer_cannot_trigger_knowledge_import():
    response = client.post("/api/knowledge/index-local", headers={"X-User": "viewer1", "X-Role": "viewer"}, json={})
    assert response.status_code == 403


def test_analyst_can_generate_report(monkeypatch):
    monkeypatch.setattr(
        report_endpoint,
        "enqueue_task",
        lambda kind, payload=None: {"task_id": "task_report_test", "kind": kind, "status": "pending", "payload": payload or {}},
    )
    monkeypatch.setattr(report_endpoint, "write_audit_log", lambda **kwargs: True)
    response = client.post(
        "/api/reports/generate",
        headers={"X-User": "analyst1", "X-Role": "analyst"},
        json={"run_id": "latest"},
    )
    assert response.status_code == 200
    assert response.json()["task_id"] == "task_report_test"


def test_developer_can_read_trace_list(monkeypatch):
    from backend.app.api.v1.endpoints import assistant as assistant_endpoint

    monkeypatch.setattr(
        "backend.app.repositories.ai_trace_repository.list_ai_traces",
        lambda identity, limit=50, session_id=None: [{"trace_id": "trace_test", "user_id": identity.user_id}],
    )
    response = client.get("/api/ai/traces", headers={"X-User": "dev1", "X-Role": "developer"})
    assert response.status_code == 200
    assert response.json()["traces"][0]["trace_id"] == "trace_test"


def test_viewer_cannot_read_trace_list():
    response = client.get("/api/ai/traces", headers={"X-User": "viewer1", "X-Role": "viewer"})
    assert response.status_code == 403


def test_developer_settings_read_guards_match_matrix_and_write_guards_stay_closed():
    developer = CurrentUser(
        user_id="dev-settings",
        username="dev-settings",
        role="developer",
        permissions=sorted(ROLE_PERMISSIONS["developer"]),
        auth_mode="test",
    )
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: developer
    try:
        for path in (
            "/api/settings/interfaces/overview",
            "/api/settings/interfaces/configs",
            "/api/settings/interfaces",
            "/api/settings/interfaces/test-logs",
        ):
            assert client.get(path).status_code == 200, path

        assert client.put(
            "/api/settings/interfaces/web", json={"display_name": "Web"}
        ).status_code == 403
        assert client.post("/api/settings/interfaces/web/test").status_code == 403
        assert client.post("/api/settings/interfaces/test-all").status_code == 403
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous


def test_analyst_cannot_read_strategy_review_history():
    analyst = CurrentUser(
        user_id="analyst-strategy",
        username="analyst-strategy",
        role="analyst",
        permissions=sorted(ROLE_PERMISSIONS["analyst"]),
        auth_mode="test",
    )
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: analyst
    try:
        response = client.get("/api/strategies/strategy-not-visible/reviews")
        assert response.status_code == 403
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous

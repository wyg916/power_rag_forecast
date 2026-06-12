from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import task as task_endpoint
from backend.app.main import app


client = TestClient(app)


def test_create_task_endpoint_returns_task_id(monkeypatch):
    def fake_enqueue(kind, payload=None):
        return {"task_id": "task_api_create", "kind": kind, "status": "pending", "payload": payload or {}}

    monkeypatch.setattr(task_endpoint, "enqueue_task", fake_enqueue)
    response = client.post("/api/tasks", json={"kind": "knowledge_import", "payload": {"limit_files": 1}})
    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "task_api_create"
    assert payload["status"] == "pending"


def test_retry_task_creates_new_task(monkeypatch):
    def fake_get(task_id):
        return {"task_id": task_id, "kind": "embedding_refresh", "status": "failed", "payload": {"x": 1}, "retry_count": 0}

    def fake_enqueue(kind, payload=None):
        return {"task_id": "task_retry_new", "kind": kind, "status": "pending", "payload": payload or {}}

    monkeypatch.setattr(task_endpoint, "get_task_record", fake_get)
    monkeypatch.setattr(task_endpoint, "enqueue_task", fake_enqueue)
    response = client.post("/api/tasks/task_old/retry", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "task_retry_new"
    assert payload["payload"]["retry_of"] == "task_old"


def test_retry_running_task_is_rejected(monkeypatch):
    monkeypatch.setattr(task_endpoint, "get_task_record", lambda task_id: {"task_id": task_id, "kind": "embedding_refresh", "status": "running"})
    response = client.post("/api/tasks/task_running/retry", json={})
    assert response.status_code == 400
    assert "cannot be retried" in response.json()["detail"]


def test_cancel_pending_task_updates_repository(monkeypatch):
    updates: list[dict] = []

    monkeypatch.setattr(task_endpoint, "get_task_record", lambda task_id: {"task_id": task_id, "kind": "knowledge_import", "status": "pending"})

    def fake_update(task_id, **kwargs):
        updates.append({"task_id": task_id, **kwargs})
        return True

    monkeypatch.setattr(task_endpoint, "update_task_runtime_state", fake_update)
    response = client.post("/api/tasks/task_pending/cancel", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "cancelled"
    assert updates[-1]["cancel_requested"] is True


def test_cancel_running_task_records_cancel_requested(monkeypatch):
    updates: list[dict] = []

    monkeypatch.setattr(task_endpoint, "get_task_record", lambda task_id: {"task_id": task_id, "kind": "knowledge_import", "status": "running"})

    def fake_update(task_id, **kwargs):
        updates.append({"task_id": task_id, **kwargs})
        return True

    monkeypatch.setattr(task_endpoint, "update_task_runtime_state", fake_update)
    response = client.post("/api/tasks/task_running/cancel", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "cancel_requested"
    assert updates[-1]["cancel_requested"] is True


def test_create_task_celery_unavailable_returns_503(monkeypatch):
    def fail_enqueue(kind, payload=None):
        raise RuntimeError("TASK_EXECUTION_MODE=celery requires available Redis/Celery worker.")

    monkeypatch.setattr(task_endpoint, "enqueue_task", fail_enqueue)
    response = client.post("/api/tasks", json={"kind": "knowledge_import", "payload": {}})
    assert response.status_code == 503
    assert "TASK_EXECUTION_MODE=celery" in response.json()["detail"]

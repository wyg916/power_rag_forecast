from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import task as task_endpoint
from backend.app.main import app
from backend.app.repositories import task_repository


client = TestClient(app)


def test_retry_rejects_when_max_retries_reached(monkeypatch):
    monkeypatch.setattr(
        task_endpoint,
        "get_task_record",
        lambda task_id: {
            "task_id": task_id,
            "kind": "embedding_refresh",
            "status": "failed",
            "retry_count": 2,
            "max_retries": 2,
            "payload": {},
        },
    )
    response = client.post("/api/tasks/task_failed/retry", json={})
    assert response.status_code == 400
    assert "retry limit exceeded" in response.json()["detail"]


def test_retry_timeout_task_creates_lineage_payload(monkeypatch):
    captured: dict = {}

    monkeypatch.setattr(
        task_endpoint,
        "get_task_record",
        lambda task_id: {
            "task_id": task_id,
            "kind": "embedding_refresh",
            "status": "timeout",
            "retry_count": 0,
            "max_retries": 2,
            "payload": {"scope": "all"},
        },
    )

    def fake_enqueue(kind, payload=None):
        captured["kind"] = kind
        captured["payload"] = payload or {}
        return {"task_id": "task_retry_new", "kind": kind, "status": "pending", "payload": captured["payload"]}

    monkeypatch.setattr(task_endpoint, "enqueue_task", fake_enqueue)
    monkeypatch.setattr(task_endpoint, "append_task_log", lambda *args, **kwargs: True)

    response = client.post("/api/tasks/task_timeout/retry", json={})
    assert response.status_code == 200
    assert response.json()["task_id"] == "task_retry_new"
    assert captured["payload"]["retry_of"] == "task_timeout"
    assert captured["payload"]["original_task_id"] == "task_timeout"
    assert captured["payload"]["retry_count"] == 1
    assert captured["payload"]["force_new"] is True


def test_cancel_running_task_records_reason(monkeypatch):
    updates: list[dict] = []
    logs: list[dict] = []
    monkeypatch.setattr(
        task_endpoint,
        "get_task_record",
        lambda task_id: {"task_id": task_id, "kind": "knowledge_import", "status": "running"},
    )
    monkeypatch.setattr(task_endpoint, "update_task_runtime_state", lambda task_id, **kwargs: updates.append({"task_id": task_id, **kwargs}) or True)
    monkeypatch.setattr(task_endpoint, "append_task_log", lambda task_id, **kwargs: logs.append({"task_id": task_id, **kwargs}) or True)

    response = client.post("/api/tasks/task_running/cancel", json={"reason": "manual stop"})
    assert response.status_code == 200
    assert response.json()["status"] == "cancel_requested"
    assert updates[-1]["cancel_requested"] is True
    assert updates[-1]["cancel_reason"] == "manual stop"
    assert logs[-1]["level"] == "warning"


def test_timeout_runtime_state_sets_finished_timestamps(monkeypatch):
    saved: list[dict] = []
    monkeypatch.setattr(
        task_repository,
        "get_task_record",
        lambda task_id: {
            "task_id": task_id,
            "kind": "forecast_run",
            "status": "running",
            "message": "running",
        },
    )
    monkeypatch.setattr(task_repository, "save_task_record", lambda record, status=None, log_text=None: saved.append({**record, "save_status": status}) or True)

    assert task_repository.update_task_runtime_state(
        "task_timeout",
        status="timeout",
        message="task timed out",
        error_code="TASK_TIMEOUT",
        timeout_seconds=1,
        finish=True,
    )
    record = saved[-1]
    assert record["status"] == "timeout"
    assert record["timeout_at"]
    assert record["finished_at"]
    assert record["error_code"] == "TASK_TIMEOUT"

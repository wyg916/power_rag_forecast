from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import task as task_endpoint
from backend.app.main import app


client = TestClient(app)


def test_task_logs_endpoint_returns_paginated_entries(monkeypatch):
    def fake_logs(task_id, *, page=1, page_size=50):
        return {
            "task_id": task_id,
            "page": page,
            "page_size": page_size,
            "total": 2,
            "items": [
                {"level": "info", "step": "prepare", "message": "accepted"},
                {"level": "error", "step": "execute", "message": "failed"},
            ],
            "text": "accepted\nfailed",
        }

    monkeypatch.setattr(task_endpoint, "list_task_log_entries", fake_logs)
    response = client.get("/api/tasks/task_logs/logs?page=2&page_size=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 2
    assert payload["page_size"] == 1
    assert payload["total"] == 2
    assert payload["items"][1]["level"] == "error"
    assert payload["items"][1]["step"] == "execute"


def test_task_logs_endpoint_limits_page_size():
    response = client.get("/api/tasks/task_logs/logs?page=1&page_size=500")
    assert response.status_code == 422

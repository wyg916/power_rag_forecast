from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import task as task_endpoint
from backend.app.main import app


client = TestClient(app)


def test_task_center_overview_endpoint(monkeypatch):
    monkeypatch.setattr(
        task_endpoint,
        "task_overview",
        lambda: {
            "task_total": 8,
            "success_total": 5,
            "running_total": 1,
            "pending_total": 1,
            "failed_total": 1,
            "timeout_total": 0,
            "queue_total": 4,
            "success_rate": 62.5,
            "day_over_day_change": {"task_total": 12.6},
        },
    )
    response = client.get("/api/tasks/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["task_total"] == 8
    assert payload["success_rate"] == 62.5


def test_task_runs_endpoint_supports_filters_and_pagination(monkeypatch):
    captured = {}

    def fake_list_task_runs(**kwargs):
        captured.update(kwargs)
        return {"list": [{"task_id": "task_1"}], "tasks": [{"task_id": "task_1"}], "total": 1, "page": kwargs["page"], "page_size": kwargs["page_size"]}

    monkeypatch.setattr(task_endpoint, "list_task_runs", fake_list_task_runs)
    response = client.get("/api/tasks/runs?task_type=price_predict&queue_name=price_predict&keyword=price&page=2&page_size=5")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert captured["task_type"] == "price_predict"
    assert captured["queue_name"] == "price_predict"
    assert captured["keyword"] == "price"
    assert captured["page"] == 2
    assert captured["page_size"] == 5


def test_recent_logs_retry_queue_trend_endpoints(monkeypatch):
    monkeypatch.setattr(task_endpoint, "recent_task_logs", lambda **kwargs: [{"task_id": "task_log", "message": "ok"}])
    monkeypatch.setattr(task_endpoint, "retry_task_candidates", lambda limit=20: [{"task_id": "task_failed"}])
    monkeypatch.setattr(task_endpoint, "queue_overview", lambda: [{"queue_name": "price_predict", "running_count": 1}])
    monkeypatch.setattr(task_endpoint, "task_trend", lambda days=7: [{"date": "2026-06-21", "success_count": 2}])

    assert client.get("/api/tasks/logs/recent?limit=3").json()["items"][0]["task_id"] == "task_log"
    assert client.get("/api/tasks/retry/recent?limit=3").json()["items"][0]["task_id"] == "task_failed"
    assert client.get("/api/tasks/queues/overview").json()["items"][0]["queue_name"] == "price_predict"
    assert client.get("/api/tasks/trend?days=7").json()["items"][0]["success_count"] == 2


def test_task_start_falls_back_to_postgres_pending_record(monkeypatch):
    monkeypatch.setattr(task_endpoint, "enqueue_task", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("celery unavailable")))
    monkeypatch.setattr(
        task_endpoint,
        "create_pending_task_record",
        lambda **kwargs: {"task_id": "task_db_1", "status": "pending", "kind": kwargs["kind"], "queue_name": kwargs["queue_name"]},
    )
    monkeypatch.setattr(task_endpoint, "write_audit_log", lambda **kwargs: None)

    response = client.post("/api/tasks/start", json={"task_type": "price_predict", "queue_name": "price_predict", "payload": {}})
    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "task_db_1"
    assert payload["status"] == "pending"
    assert "dispatch_fallback_reason" in payload


def test_task_start_dispatches_business_task_types(monkeypatch):
    captured: list[tuple[str, dict]] = []

    def fake_enqueue(kind, payload=None):
        captured.append((kind, payload or {}))
        return {"task_id": f"task_{kind}", "status": "pending", "kind": kind, "payload": payload or {}}

    monkeypatch.setattr(task_endpoint, "enqueue_task", fake_enqueue)
    monkeypatch.setattr(task_endpoint, "write_audit_log", lambda **kwargs: None)

    for kind in ["price_predict", "data_sync", "report_daily"]:
        response = client.post("/api/tasks/start", json={"task_type": kind, "payload": {"source": "test"}})
        assert response.status_code == 200
        assert response.json()["kind"] == kind

    assert [item[0] for item in captured] == ["price_predict", "data_sync", "report_daily"]


def test_task_retry_falls_back_to_postgres_pending_record(monkeypatch):
    monkeypatch.setattr(
        task_endpoint,
        "get_task_record",
        lambda task_id: {"task_id": task_id, "kind": "price_predict", "status": "failed", "retry_count": 0, "max_retries": 2, "payload": {}, "queue_name": "price_predict"},
    )
    monkeypatch.setattr(task_endpoint, "enqueue_task", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("celery unavailable")))
    monkeypatch.setattr(task_endpoint, "append_task_log", lambda *args, **kwargs: True)
    monkeypatch.setattr(task_endpoint, "write_audit_log", lambda **kwargs: None)
    monkeypatch.setattr(
        task_endpoint,
        "create_pending_task_record",
        lambda **kwargs: {"task_id": "task_db_retry", "status": "pending", "kind": kwargs["kind"], "queue_name": kwargs["queue_name"]},
    )

    response = client.post("/api/tasks/task_failed/retry", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "task_db_retry"
    assert payload["status"] == "pending"


def test_task_detail_and_logs_return_repository_payload(monkeypatch):
    monkeypatch.setattr(
        task_endpoint,
        "get_task_record",
        lambda task_id: {
            "task_id": task_id,
            "kind": "price_predict",
            "status": "success",
            "payload_json": {"horizon": 24},
            "result_json": {"run_id": "forecast_1"},
        },
    )
    monkeypatch.setattr(
        task_endpoint,
        "list_task_log_entries",
        lambda task_id, page=1, page_size=50: {
            "task_id": task_id,
            "page": page,
            "page_size": page_size,
            "total": 1,
            "items": [{"level": "info", "step": "persist", "message": "done"}],
        },
    )

    detail = client.get("/api/tasks/task_price_1")
    logs = client.get("/api/tasks/task_price_1/logs")
    assert detail.status_code == 200
    assert detail.json()["result_json"]["run_id"] == "forecast_1"
    assert logs.status_code == 200
    assert logs.json()["items"][0]["step"] == "persist"

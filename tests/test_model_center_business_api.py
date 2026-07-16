from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import model as model_endpoint
from backend.app.main import app


client = TestClient(app)


def test_model_center_overview_endpoint_contract(monkeypatch):
    def fake_overview(**_: object) -> dict:
        return {
            "available": True,
            "active": {"model_version": "v3.2.1", "status": "Active"},
            "candidate": {"model_version": "v3.3.0-rc1", "status": "Candidate"},
            "versions": [{"model_version": "v3.2.1"}, {"model_version": "v3.3.0-rc1"}],
            "effect": [{"time": "06-21 00:00", "actual": 100, "active": 102, "candidate": 101, "diff": -1, "data_origin": "seed"}],
            "error_trend": [{"date": "06-21", "mae": 15.42, "rmse": 23.67, "mape": 7.21}],
            "admission": {"rules": [], "passed": True, "conclusion": "满足准入条件"},
            "evaluation_summary": [],
            "training": {"task_id": "train_1", "status": "success"},
            "rollback": {"options": []},
            "events": [],
            "data_lineage": {"effect": "postgresql.model_prediction_comparison_points"},
        }

    monkeypatch.setattr(model_endpoint, "model_center_overview", fake_overview)
    response = client.get("/api/models/center/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["active"]["model_version"] == "v3.2.1"
    assert payload["candidate"]["status"] == "Candidate"
    assert payload["effect"]
    assert payload["data_lineage"]["effect"] == "postgresql.model_prediction_comparison_points"


def test_model_center_version_detail_endpoint(monkeypatch):
    monkeypatch.setattr(
        model_endpoint,
        "model_version_detail",
        lambda version, **_: {
            "available": True,
            "version": {"model_version": version, "status": "Candidate"},
            "latest_metric": {"mae": 15.42},
            "metrics_history": [{"metric_date": "2025-06-21", "mae": 15.42}],
            "events": [{"event_id": "evt_1", "action": "model.activate"}],
            "prediction_samples": [{"time": "06-21 00:00", "actual_value": 100}],
        },
    )
    response = client.get("/api/models/center/versions/v3.3.0-rc1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["version"]["model_version"] == "v3.3.0-rc1"
    assert payload["metrics_history"]


def test_model_center_training_start_endpoint(monkeypatch):
    monkeypatch.setattr(model_endpoint, "start_model_training", lambda user, payload: {"task_id": "train_x", "status": "pending"})
    monkeypatch.setattr(model_endpoint, "write_audit_log", lambda **_: True)
    response = client.post("/api/models/center/training/start", json={"model_type": "负荷预测模型", "region": "浙江省"})
    assert response.status_code == 200
    assert response.json()["task_id"] == "train_x"


def test_model_center_activate_endpoint(monkeypatch):
    monkeypatch.setattr(
        model_endpoint,
        "activate_model_version",
        lambda version, user, reason, **_: {"success": True, "active_version": version},
    )
    monkeypatch.setattr(model_endpoint, "write_audit_log", lambda **_: True)
    response = client.post("/api/models/center/activate", json={"version": "v3.3.0-rc1", "reason": "test"})
    assert response.status_code == 200
    assert response.json()["active_version"] == "v3.3.0-rc1"

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import stage1_services
from backend.app.main import app
from backend.app.platform_services import generate_anomaly_explanations, generate_strategy_advice


client = TestClient(app)


def test_web_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "售电交易" in payload["platform"]


def test_dashboard_endpoint_returns_core_shape():
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
    assert "forecast" in payload
    assert "data_sources" in payload
    assert isinstance(payload["data_sources"], list)
    if payload["data_sources"]:
        assert "\\" not in payload["data_sources"][0].get("source", "")
        assert "source_url" in payload["data_sources"][0]


def test_forecast_latest_endpoint_is_safe():
    response = client.get("/api/forecast/latest")
    assert response.status_code == 200
    payload = response.json()
    assert "available" in payload
    assert "records" in payload


def test_ai_insights_endpoint_returns_sections():
    response = client.get("/api/ai/insights")
    assert response.status_code == 200
    payload = response.json()
    assert "sections" in payload
    assert "forecast" in payload["sections"]
    assert "AI" in payload["sections"]["forecast"]["title"]


def test_scheduled_tasks_endpoint_is_safe():
    response = client.get("/api/scheduled-tasks")
    assert response.status_code == 200
    payload = response.json()
    assert "available" in payload
    assert "tasks" in payload


def test_strategy_and_anomaly_services_are_data_bound():
    strategy = generate_strategy_advice(persist=False)
    anomaly = generate_anomaly_explanations(persist=False)
    assert "items" in strategy
    assert "items" in anomaly
    if strategy["items"]:
        first = strategy["items"][0]
        assert "target_hour" in first
        assert "evidence" in first
    if anomaly["items"]:
        first = anomaly["items"][0]
        assert "target_hour" in first
        assert "evidence" in first


def test_stage1_standard_interfaces_return_core_shape():
    endpoints = [
        "/api/prediction/latest?market=DOM",
        "/api/prediction/detail?market=DOM",
        "/api/market/history?market=DOM",
        "/api/weather/forecast",
        "/api/load/forecast?market=DOM",
        "/api/renewable/forecast?market=DOM",
        "/api/model/explain?market=DOM",
        "/api/risk/level?market=DOM",
    ]
    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 200, endpoint
        payload = response.json()
        assert "available" in payload, endpoint

    prediction = client.get("/api/prediction/latest?market=广东&date=2099-01-01").json()
    assert prediction["market_matched"] is False
    assert prediction["messages"]


def test_prediction_latest_empty_messages_contract(monkeypatch):
    calls = []

    def fake_latest():
        calls.append("read")
        return {
            "available": False,
            "records": [],
            "message": "隔离测试库当前没有预测结果。",
            "run_id": "empty-run",
            "source": "isolated.forecast_results",
            "source_type": "postgresql",
        }

    monkeypatch.setattr(stage1_services, "load_latest_forecast", fake_latest)
    response = client.get("/api/prediction/latest?market=广东&date=2099-01-01")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["market_matched"] is False
    assert isinstance(payload["messages"], list) and payload["messages"]
    assert "隔离测试库当前没有预测结果。" in payload["messages"]
    assert payload["run_id"] == "empty-run"
    assert payload["source_type"] == "postgresql"
    assert calls == ["read"]


def test_prediction_latest_data_messages_contract(monkeypatch):
    calls = []

    def fake_latest():
        calls.append("read")
        return {
            "available": True,
            "records": [
                {"datetime": "2099-01-01T00:00:00", "predicted_price": 100.0},
                {"datetime": "2099-01-01T01:00:00", "predicted_price": 120.0},
            ],
            "run_id": "data-run",
            "source": "isolated.forecast_results",
            "source_type": "postgresql",
        }

    monkeypatch.setattr(stage1_services, "load_latest_forecast", fake_latest)
    monkeypatch.setattr(stage1_services, "_main_factors", lambda _df, _pcol: ["隔离测试因素"])
    monkeypatch.setattr(stage1_services, "_model_confidence", lambda: 0.8)
    response = client.get("/api/prediction/latest?market=DOM&date=2099-01-01")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["messages"] == []
    assert payload["run_id"] == "data-run"
    assert payload["source_type"] == "postgresql"
    assert len(payload["records"]) == 2
    assert calls == ["read"]


def test_model_gateway_health_and_chat_feedback():
    gateway = client.get("/api/model-gateway/health")
    assert gateway.status_code == 200
    gateway_payload = gateway.json()
    assert gateway_payload["ok"] is True
    assert gateway_payload.get("model") or gateway_payload.get("default_provider")

    feedback = client.post(
        "/api/ai/chat/feedback",
        json={"session_id": "test_session", "trace_id": "trace_test", "rating": "up", "comment": "ok"},
    )
    assert feedback.status_code == 200
    assert feedback.json()["ok"] is True


def test_stage2_agent_endpoint_shape():
    response = client.post(
        "/api/ai/agent/analyze",
        json={"question": "\u5e2e\u6211\u751f\u6210\u4eca\u5929\u7535\u4ef7\u98ce\u9669\u6458\u8981", "market": "DOM", "debug": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"]
    assert isinstance(payload["workflow"], list)
    assert isinstance(payload["agent_trace"], list)
    assert isinstance(payload["data_used"], dict)


def test_database_table_browser_endpoints_are_safe():
    response = client.get("/api/data/datasets")
    assert response.status_code == 200
    payload = response.json()
    assert "available" in payload
    assert "datasets" in payload
    if payload["datasets"]:
        dataset_id = payload["datasets"][0]["dataset_id"]
        rows = client.get(f"/api/data/datasets/{dataset_id}/rows?page_size=5")
        assert rows.status_code == 200
        row_payload = rows.json()
        assert row_payload["dataset_id"] == dataset_id
        assert "columns" in row_payload
        assert "records" in row_payload

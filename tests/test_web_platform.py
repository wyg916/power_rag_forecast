from __future__ import annotations

from fastapi.testclient import TestClient

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
    response = client.get("/api/data/tables")
    assert response.status_code == 200
    payload = response.json()
    assert "available" in payload
    assert "tables" in payload
    if payload["tables"]:
        table_name = payload["tables"][0]["table_name"]
        rows = client.get(f"/api/data/tables/{table_name}/rows?limit=5")
        assert rows.status_code == 200
        row_payload = rows.json()
        assert row_payload["table_name"] == table_name
        assert "columns" in row_payload
        assert "records" in row_payload

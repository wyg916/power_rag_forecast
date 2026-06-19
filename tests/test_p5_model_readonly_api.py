from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import model as model_endpoint
from backend.app.main import app


client = TestClient(app)


def test_p2_backtest_summary_payload_reads_metrics():
    payload = model_endpoint.p2_backtest_summary_payload()
    assert payload["available"] is True
    assert payload["metrics"]
    assert payload["reference_baseline"]["model"] == "persistence_24h"
    assert "baseline_methods" in payload
    assert "report_excerpt" in payload


def test_p2_feature_schema_payload_reports_schema_gate():
    payload = model_endpoint.p2_feature_schema_payload()
    assert payload["available"] is True
    assert payload["schema_gate"]["ok"] is True
    assert payload["feature_count"] >= 1
    assert payload["feature_sample"]
    assert payload["target"]["name"] == "da_price"


def test_p2_leakage_check_payload_reports_gate_status():
    payload = model_endpoint.p2_leakage_check_payload()
    assert payload["available"] is True
    assert payload["gate_status"] == "passed"
    assert payload["high_risk_count"] == 0
    assert payload["checks"]["time_split_chronological"] is True


def test_p5_model_readonly_endpoints_are_available():
    for path in [
        "/api/models/backtest/summary",
        "/api/models/feature-schema",
        "/api/models/leakage-check",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["available"] is True

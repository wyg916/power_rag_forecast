from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.ai_assistant.templates.deterministic_answers import answer_data_sql_query
from backend.app.main import app
from backend.app.services import data_trust_service
from backend.app.services.controlled_business_query_service import query_business_data
from backend.app.services.dataset_query_service import dataset_fields, list_registered_datasets


client = TestClient(app)
ANALYST = {"X-User": "day4_analyst", "X-Role": "analyst"}


def test_dataset_catalog_and_field_mapping_hide_physical_objects():
    catalog = list_registered_datasets(search="天气")
    assert catalog["available"] is True
    item = next(row for row in catalog["datasets"] if row["dataset_id"] == "weather_observations")
    assert "object_name" not in item
    assert "table_name" not in item
    fields = dataset_fields("weather_observations")
    assert any(field["field_id"] == "temperature_c" for field in fields["fields"])
    assert all("column_name" not in field for field in fields["fields"])


def test_legacy_free_sql_function_is_permanently_disabled(monkeypatch):
    monkeypatch.setattr(data_trust_service, "database_engine", lambda: (_ for _ in ()).throw(AssertionError("database reached")))
    for statement in (
        "SELECT 1",
        "SELECT * FROM users",
        "SELECT pg_read_file('postgresql.conf')",
        "DELETE FROM raw_weather",
    ):
        result = data_trust_service.execute_read_only_sql(statement)
        assert result["available"] is False
        assert result["safe"] is False
        assert "永久禁用" in result["not_found_reason"]
        assert "sql" not in result


def test_controlled_ai_business_query_uses_registered_dataset_and_public_fields():
    result = query_business_data("请查一下天气观测最新 2 条温度数据", dataset_ids=["weather_observations"], limit=2)
    assert result["safe"] is True
    assert result["dataset_id"] == "weather_observations"
    assert "temperature_c" in result["fields"]
    assert result["query_summary"]
    assert len(result["records"]) <= 2
    assert all("raw_json" not in row and "source_file" not in row for row in result["records"])
    answer = answer_data_sql_query(result)
    assert "数据集：weather_observations" in answer
    assert "受控数据集查询" in answer


def test_ai_query_blocks_sensitive_and_unregistered_objects():
    for target in ("users", "audit_logs", "pg_authid", "information_schema"):
        result = query_business_data(f"查询 {target}", dataset_ids=[target])
        assert result["available"] is False
        assert result["safe"] is False
        assert result["records"] == []


def test_ai_catalog_empty_dataset_and_readiness_use_dataset_contract():
    catalog = query_business_data("当前数据库有哪些核心业务表？")
    assert catalog["query_type"] == "data_catalog_list"
    assert "dataset_id" in catalog["fields"]
    assert all("table_name" not in row for row in catalog["records"])

    empty = query_business_data("哪些数据集当前为空？")
    assert empty["query_type"] == "empty_dataset_scan"
    assert "查询摘要" in answer_data_sql_query(empty)

    readiness = query_business_data("当前数据是否足够支撑预测？")
    assert readiness["query_type"] == "prediction_readiness"
    assert readiness["dataset_id"] == "prediction_readiness"


def test_data_endpoints_expose_only_registered_contract_and_sql_returns_410():
    catalog = client.get("/api/data/catalog", headers=ANALYST)
    fields = client.get("/api/data/fields?dataset_id=weather_observations", headers=ANALYST)
    blocked = client.post("/api/data/sql/query", headers=ANALYST, json={"sql": "SELECT * FROM users"})
    assert catalog.status_code == 200 and catalog.json()["datasets"]
    assert fields.status_code == 200 and fields.json()["fields"]
    assert blocked.status_code == 410
    assert blocked.json()["detail"] == {
        "code": "arbitrary_sql_disabled",
        "message": "任意 SQL 查询接口已永久禁用，请使用已注册数据集接口。",
    }


def test_ai_chat_business_data_query_uses_controlled_tool():
    developer = {"X-User": "day4_developer", "X-Role": "developer"}
    response = client.post(
        "/api/ai/chat",
        headers=developer,
        json={"question": "请查询 raw_weather 最新 2 条记录", "debug": True},
    )
    assert response.status_code == 200
    payload = response.json()
    query_calls = [item for item in payload["tool_calls"] if item["tool_name"] == "query_business_data"]
    assert query_calls
    assert query_calls[0]["output"]["safe"] is True
    assert query_calls[0]["output"]["dataset_id"] == "weather_observations"
    assert payload["data_used"]["data_query"] is True

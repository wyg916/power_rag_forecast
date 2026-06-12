from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from backend.app.ai_assistant.core.intent_router import route_intent
from backend.app.ai_assistant.templates.deterministic_answers import answer_data_sql_query
from backend.app.main import app
from backend.app.services import data_trust_service


client = TestClient(app)


def _sqlite_engine():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE raw_weather (datetime TEXT, temperature REAL, humidity REAL)"))
        conn.execute(
            text(
                """
                INSERT INTO raw_weather (datetime, temperature, humidity)
                VALUES
                    ('2026-06-10 00:00:00', 22.5, 61.0),
                    ('2026-06-11 00:00:00', 24.2, 58.0)
                """
            )
        )
    return engine


def test_data_catalog_and_field_mapping_are_available_without_database():
    catalog = data_trust_service.get_data_catalog(search="天气")
    assert catalog["available"] is True
    assert any(item["table_name"] == "raw_weather" for item in catalog["datasets"])

    fields = data_trust_service.get_field_mappings(table="raw_weather")
    assert fields["available"] is True
    assert any(item["field_name"] == "temperature" for item in fields["fields"])


def test_freshness_and_read_only_sql_use_catalog_allowlist(monkeypatch):
    engine = _sqlite_engine()
    monkeypatch.setattr(data_trust_service, "database_engine", lambda: engine)

    freshness = data_trust_service.get_data_freshness_report(["raw_weather"])
    item = freshness["items"][0]
    assert item["available"] is True
    assert item["row_count"] == 2
    assert item["datetime_field"] == "datetime"
    assert item["min_datetime"] == "2026-06-10 00:00:00"
    assert item["max_datetime"] == "2026-06-11 00:00:00"

    result = data_trust_service.execute_read_only_sql(
        "SELECT datetime, temperature FROM raw_weather ORDER BY datetime DESC",
        limit=1,
    )
    assert result["available"] is True
    assert result["safe"] is True
    assert result["tables"] == ["raw_weather"]
    assert result["row_count"] == 1

    blocked_write = data_trust_service.execute_read_only_sql("DELETE FROM raw_weather")
    assert blocked_write["available"] is False
    assert blocked_write["safe"] is False
    assert "禁止关键字" in blocked_write["not_found_reason"] or "只允许 SELECT" in blocked_write["not_found_reason"]

    blocked_table = data_trust_service.execute_read_only_sql("SELECT * FROM users")
    assert blocked_table["available"] is False
    assert blocked_table["safe"] is False
    assert "不允许查数" in blocked_table["not_found_reason"]


def test_ai_business_data_query_answer_explains_query_contract(monkeypatch):
    engine = _sqlite_engine()
    monkeypatch.setattr(data_trust_service, "database_engine", lambda: engine)

    decision = route_intent("请查一下 raw_weather 最新 2 条温度数据")
    assert decision.intent == "data_sql_query"
    assert decision.entities["tables"] == ["raw_weather"]
    assert decision.entities["limit"] == 2

    result = data_trust_service.query_business_data("请查一下 raw_weather 最新 2 条温度数据", tables=["raw_weather"], limit=2)
    assert result["available"] is True
    assert result["table_name"] == "raw_weather"
    assert "temperature" in result["fields"]
    assert result["query_summary"]
    assert result["time_range"]["field"] == "datetime"

    answer = answer_data_sql_query(result)
    assert "表名：raw_weather" in answer
    assert "字段：" in answer
    assert "时间范围：" in answer
    assert "查询摘要：" in answer


def test_ai_chat_business_data_query_uses_read_only_tool(monkeypatch):
    engine = _sqlite_engine()
    monkeypatch.setattr(data_trust_service, "database_engine", lambda: engine)

    response = client.post("/api/ai/chat", json={"question": "请查一下 raw_weather 最新 2 条温度数据", "debug": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "data_sql_query"
    assert payload["tool_calls"][0]["tool_name"] == "query_business_data"
    assert payload["tool_calls"][0]["output"]["safe"] is True
    assert "表名：raw_weather" in payload["answer"]
    assert "字段：" in payload["answer"]
    assert "时间范围：" in payload["answer"]
    assert payload["data_used"]["data_query"] is True


def test_data_catalog_and_sql_endpoints_are_safe():
    catalog = client.get("/api/data/catalog")
    assert catalog.status_code == 200
    assert catalog.json()["available"] is True
    assert catalog.json()["datasets"]

    fields = client.get("/api/data/fields?table=raw_weather")
    assert fields.status_code == 200
    assert fields.json()["available"] is True

    blocked = client.post("/api/data/sql/query", json={"sql": "DROP TABLE raw_weather", "limit": 10})
    assert blocked.status_code == 200
    payload = blocked.json()
    assert payload["available"] is False
    assert payload["safe"] is False

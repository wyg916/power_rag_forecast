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
    assert "敏感表" in blocked_table["not_found_reason"]


def test_read_only_sql_blocks_sensitive_tables_dangerous_statements_and_functions(monkeypatch):
    engine = _sqlite_engine()
    monkeypatch.setattr(data_trust_service, "database_engine", lambda: engine)

    blocked_cases = [
        ("SELECT * FROM users", "敏感表"),
        ("SELECT * FROM audit_logs", "敏感表"),
        ("INSERT INTO raw_weather (datetime) VALUES ('2026-06-12')", "只允许 SELECT"),
        ("UPDATE raw_weather SET temperature = 1", "只允许 SELECT"),
        ("DELETE FROM raw_weather", "只允许 SELECT"),
        ("DROP TABLE raw_weather", "只允许 SELECT"),
        ("TRUNCATE TABLE raw_weather", "只允许 SELECT"),
        ("ALTER TABLE raw_weather ADD COLUMN x INT", "只允许 SELECT"),
        ("CREATE TABLE x (id INT)", "只允许 SELECT"),
        ("SELECT * FROM raw_weather; SELECT * FROM raw_weather", "单条 SELECT"),
        ("SELECT * FROM information_schema.tables", "系统 schema"),
        ("SELECT * FROM pg_catalog.pg_tables", "系统 schema"),
        ("SELECT pg_sleep(1)", "危险函数"),
    ]

    for sql, reason in blocked_cases:
        result = data_trust_service.execute_read_only_sql(sql)
        assert result["available"] is False, sql
        assert result["safe"] is False, sql
        assert reason in result["not_found_reason"], result["not_found_reason"]


def test_read_only_sql_enforces_maximum_result_limit(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE raw_weather (datetime TEXT, temperature REAL, humidity REAL)"))
        for idx in range(600):
            conn.execute(
                text("INSERT INTO raw_weather (datetime, temperature, humidity) VALUES (:dt, :temperature, :humidity)"),
                {"dt": f"2026-06-01 {idx % 24:02d}:00:00", "temperature": float(idx), "humidity": 50.0},
            )
    monkeypatch.setattr(data_trust_service, "database_engine", lambda: engine)

    result = data_trust_service.execute_read_only_sql("SELECT datetime, temperature FROM raw_weather ORDER BY temperature DESC", limit=9999)

    assert result["safe"] is True
    assert result["available"] is True
    assert result["limit"] == 500
    assert result["row_count"] == 500


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


def test_ai_catalog_empty_table_and_prediction_readiness_questions_route_to_query_tool(monkeypatch):
    engine = _sqlite_engine()
    monkeypatch.setattr(data_trust_service, "database_engine", lambda: engine)

    catalog_decision = route_intent("当前数据库有哪些核心业务表？")
    assert catalog_decision.intent == "data_sql_query"
    catalog = data_trust_service.query_business_data("当前数据库有哪些核心业务表？")
    assert catalog["query_type"] == "data_catalog_list"
    assert catalog["available"] is True
    assert "table_name" in catalog["fields"]

    empty_decision = route_intent("哪些表当前为空？")
    assert empty_decision.intent == "data_sql_query"
    empty = data_trust_service.query_business_data("哪些表当前为空？")
    assert empty["query_type"] == "empty_table_scan"
    assert empty["available"] is True
    assert "查询摘要" in answer_data_sql_query(empty)

    readiness_decision = route_intent("当前数据是否足够支撑预测？")
    assert readiness_decision.intent == "data_sql_query"
    readiness = data_trust_service.query_business_data("当前数据是否足够支撑预测？")
    assert readiness["query_type"] == "prediction_readiness"
    assert "raw_market" in readiness["table_name"]


def test_ai_query_blocks_sensitive_users_table():
    decision = route_intent("查询 users 表看看。")
    assert decision.intent == "data_sql_query"
    assert decision.entities["tables"] == ["users"]

    result = data_trust_service.query_business_data("查询 users 表看看。", tables=["users"])
    assert result["available"] is False
    assert result["safe"] is False
    assert "敏感" in result["not_found_reason"]


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

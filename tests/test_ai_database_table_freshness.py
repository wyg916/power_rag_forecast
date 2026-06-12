from __future__ import annotations

from backend.app.ai_assistant.core.intent_router import route_intent
from backend.app.ai_assistant.templates.deterministic_answers import answer_data_freshness


def test_table_names_are_routed_to_database_freshness_intent():
    decision = route_intent("raw_market raw_load raw_weather forecast_results 这几个表在数据库中最新的数据是几号？")

    assert decision.intent == "database_table_freshness"
    assert decision.entities["tables"] == ["raw_market", "raw_load", "raw_weather", "forecast_results"]


def test_multi_table_freshness_answer_lists_missing_and_available_tables():
    answer = answer_data_freshness(
        {
            "multi_table": True,
            "available": True,
            "items": [
                {
                    "table": "raw_market",
                    "available": True,
                    "min_datetime": "2024-01-01",
                    "max_datetime": "2026-06-01",
                    "row_count": 10,
                    "datetime_field": "datetime",
                },
                {"table": "forecast_results", "available": False, "message": "未找到该数据库表或视图。"},
            ],
        },
        "数据库表",
    )

    assert "raw_market" in answer
    assert "forecast_results" in answer
    assert "最新时间 2026-06-01" in answer
    assert "未找到" in answer

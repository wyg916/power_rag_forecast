from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def _ask(question: str) -> dict:
    response = client.post("/api/ai/chat", json={"question": question, "debug": True})
    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"]
    assert "必须买入" not in payload["answer"]
    assert "保证收益" not in payload["answer"]
    return payload


def test_ai_assistant_hides_debug_fields_by_default():
    response = client.post("/api/ai/chat", json={"question": "今天星期几？"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"]
    for field in ["intent", "tools", "tool_calls", "trace", "agent_trace", "workflow"]:
        assert field not in payload
    assert "AI意图" not in payload["answer"]
    assert "Trace" not in payload["answer"]


def test_ai_assistant_forecast_extreme_is_question_specific():
    payload = _ask("\u660e\u5929\u4ec0\u4e48\u65f6\u5019\u7535\u4ef7\u6700\u9ad8\uff1f")
    assert payload["intent"] == "forecast_max_price"
    assert payload["evidence"]
    assert payload["tool_calls"][0]["tool_name"] == "get_forecast_metrics"
    assert "\u6700\u9ad8\u7535\u4ef7" in payload["answer"] or "\u6700\u9ad8\u4ef7" in payload["answer"]


def test_ai_assistant_hour_explain_uses_hour_tool():
    payload = _ask("\u4e3a\u4ec0\u4e4818\u70b9\u98ce\u9669\u9ad8\uff1f")
    assert payload["intent"] == "risk_reason"
    assert [call["tool_name"] for call in payload["tool_calls"]] == ["explain_high_price_hour"]
    assert "18:00" in payload["answer"]


def test_ai_assistant_core_intents():
    cases = {
        "\u54ea\u4e9b\u5c0f\u65f6\u98ce\u9669\u6700\u9ad8\uff1f": "forecast_risk_hours",
        "\u4eca\u5929\u4ea4\u6613\u7b56\u7565\u600e\u4e48\u505a\uff1f": "trading_risk_summary",
        "\u54ea\u4e9b\u5c0f\u65f6\u9002\u5408\u50a8\u80fd\u653e\u7535\uff1f": "storage_discharge_advice",
        "\u6a21\u578b\u6700\u8fd1\u8bef\u5dee\u53d8\u5927\u4e86\u5417\uff1f": "model_error_status",
        "\u4eca\u5929\u65e5\u62a5\u6838\u5fc3\u7ed3\u8bba\u662f\u4ec0\u4e48\uff1f": "report_summary",
        "\u4eca\u5929\u6570\u636e\u66f4\u65b0\u4e86\u5417\uff1f": "database_table_freshness",
    }
    for question, intent in cases.items():
        payload = _ask(question)
        assert payload["intent"] == intent
        assert payload["evidence"]
        assert payload["tool_calls"]


def test_stage1_acceptance_questions_are_answerable():
    cases = {
        "\u660e\u5929\u5e7f\u4e1c\u7535\u4ef7\u600e\u4e48\u770b\uff1f": "trading_risk_summary",
        "\u4e3a\u4ec0\u4e48\u660e\u5929\u7535\u4ef7\u53ef\u80fd\u4e0a\u6da8\uff1f": "trading_risk_summary",
        "\u665a\u9ad8\u5cf0\u6709\u6ca1\u6709\u9ad8\u4ef7\u98ce\u9669\uff1f": "forecast_risk_hours",
        "\u5f53\u524d\u9884\u6d4b\u7ed3\u679c\u4e3b\u8981\u53d7\u54ea\u4e9b\u56e0\u7d20\u5f71\u54cd\uff1f": "trading_risk_summary",
        "\u8d1f\u8377\u504f\u9ad8\u4e3a\u4ec0\u4e48\u4f1a\u63a8\u9ad8\u7535\u4ef7\uff1f": "trading_risk_summary",
        "\u65b0\u80fd\u6e90\u51fa\u529b\u4e0b\u964d\u4f1a\u9020\u6210\u4ec0\u4e48\u5f71\u54cd\uff1f": "trading_risk_summary",
        "\u8fd9\u4e2a\u9884\u6d4b\u7ed3\u679c\u53ef\u9760\u5417\uff1f": "model_error_status",
        "\u5e2e\u6211\u751f\u6210\u4e00\u6bb5\u4eca\u5929\u7684\u7535\u4ef7\u5206\u6790\u65e5\u62a5\u3002": "report_summary",
    }
    for question, intent in cases.items():
        response = client.post("/api/ai/chat", json={"question": question, "market": "\u5e7f\u4e1c", "debug": True})
        assert response.status_code == 200
        payload = response.json()
        assert payload["intent"] == intent
        assert payload["answer"]
        assert payload["trace_id"].startswith("trace_")
        assert isinstance(payload["data_used"], dict)
        assert isinstance(payload["suggestions"], list)
        assert "必须买入" not in payload["answer"]
        assert "保证收益" not in payload["answer"]


def test_weather_question_answers_weather_not_power_price():
    payload = _ask("\u660e\u5929\u5929\u6c14\u600e\u4e48\u6837\uff1f")
    assert payload["intent"] == "weather_summary"
    assert payload["data_used"]["weather"] is True
    assert "\u5929\u6c14" in payload["answer"] or "\u6c14\u6e29" in payload["answer"]
    assert "\u6700\u9ad8\u7535\u4ef7" not in payload["answer"]


def test_stage2_agent_analyze_runs_multi_agent_workflow():
    response = client.post(
        "/api/ai/agent/analyze",
            json={
                "question": "\u5e2e\u6211\u5206\u6790\u660e\u5929\u5e7f\u4e1c\u7535\u4ef7\u4e0a\u6da8\u539f\u56e0\uff0c\u5e76\u7ed9\u51fa\u4ea4\u6613\u98ce\u9669\u63d0\u793a\u3002",
                "market": "\u5e7f\u4e1c",
                "debug": True,
            },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "trading_risk_summary"
    assert payload["complexity"] == "complex"
    assert payload["answer"]
    for node in ["input_normalizer", "context_resolver", "intent_router", "tool_executor", "answer_guard"]:
        assert node in payload["workflow"]
    assert len(payload["agent_trace"]) >= 5
    used = payload["data_used"]
    assert used["prediction"] is True
    assert used["weather"] is True
    assert used["model"] is True
    assert "交易" in payload["answer"] or "风险" in payload["answer"]


def test_chat_uses_stage2_agent_for_complex_business_question():
    payload = _ask("\u660e\u5929\u5e7f\u4e1c\u7535\u4ef7\u4e0a\u6da8\u539f\u56e0\u548c\u4ea4\u6613\u98ce\u9669\u662f\u4ec0\u4e48\uff1f")
    assert payload["intent"] == "trading_risk_summary"
    assert "workflow" in payload
    assert "tool_executor" in payload["workflow"]
    assert payload["data_used"]["prediction"] is True
    assert payload["data_used"]["weather"] is True
    assert "\u5929\u6c14\u600e\u4e48\u6837" not in payload["answer"]

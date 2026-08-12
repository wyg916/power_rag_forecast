from __future__ import annotations

from types import SimpleNamespace

from backend.app.ai_assistant import service
from backend.app.ai_assistant.core.intent_router import route_intent
from backend.app.ai_assistant.core.tool_router import tools_for_intent
from backend.app.ai_assistant.schemas import IntentDecision


def _result(name: str, output: dict):
    return SimpleNamespace(name=name, output=output)


def test_explanation_questions_route_to_question_specific_answers():
    assert route_intent("用通俗的话解释日前电价和实时电价有什么区别。").intent == "market_price_explanation"
    assert route_intent("用通俗的话说明为什么负荷高时电价可能上涨。").intent == "load_price_explanation"
    assert route_intent("用通俗的话说明预测误差为什么需要人工复核。").intent == "forecast_error_explanation"
    assert route_intent("生成一段适合经营例会的负荷与天气影响摘要。").intent == "load_weather_summary"
    assert tools_for_intent("load_weather_summary") == ["get_load_summary", "get_weather_summary"]


def test_forecast_error_answer_contains_business_impact_and_review_steps():
    answer = service._build_answer(
        IntentDecision("forecast_error_explanation", 1.0, {}, "预测误差为什么需要人工复核"),
        [_result("get_model_error_summary", {"error_rows": []})],
    )

    assert "实时补购成本" in answer
    assert "复核步骤" in answer
    assert "自动切换模型" in answer


def test_high_risk_action_question_returns_three_actions():
    answer = service._build_answer(
        IntentDecision("forecast_risk_hours", 1.0, {}, "针对高价风险窗口给出三条可执行建议"),
        [_result("get_high_risk_hours", {"items": [{"hour": "18:00", "risk_level": "高", "predicted_price": 116.0}]})],
    )

    assert all(marker in answer for marker in ["1.", "2.", "3."])
    assert "人工确认" in answer


def test_model_error_action_question_has_recovery_sequence():
    answer = service._build_answer(
        IntentDecision("model_error_status", 1.0, {}, "模型误差扩大时如何处置"),
        [_result("get_model_error_summary", {"error_rows": []})],
    )

    assert "处置建议" in answer
    assert "真实值回填" in answer
    assert "单次偏差" in answer


def test_load_weather_summary_uses_both_database_backed_tool_results():
    answer = service._build_answer(
        IntentDecision("load_weather_summary", 1.0, {}, "负荷与天气影响摘要"),
        [
            _result("get_load_summary", {"avg_load": 957.5, "max_load": 1015.0, "min_load": 900.0}),
            _result("get_weather_summary", {"city": "TEST", "avg_temperature": 15.75, "max_temperature": 21.5, "min_temperature": 10.0}),
        ],
    )

    assert "957.50 MW" in answer
    assert "10.00 至 21.50 摄氏度" in answer
    assert "时间窗口是否一致" in answer


def test_report_summary_has_storage_and_publication_review_boundaries():
    payload = {
        "report_id": "report-1",
        "available": True,
        "summary": {
            "executive_summary": {
                "record_count": 24,
                "average_price": 103.0,
                "maximum_price": 126.0,
                "minimum_price": 80.0,
                "peak_valley_spread": 46.0,
            }
        },
    }
    storage = service._build_answer(
        IntentDecision("report_summary", 1.0, {}, "生成储能策略复核摘要，并说明决策边界"),
        [_result("get_report_summary", payload)],
    )
    publish = service._build_answer(
        IntentDecision("report_summary", 1.0, {}, "生成报告发布前的证据完整性摘要"),
        [_result("get_report_summary", payload)],
    )

    assert "SOC" in storage and "不等同于交易或调度指令" in storage
    assert "发布前检查" in publish and "运行标识" in publish
    assert "{'record_count'" not in storage + publish

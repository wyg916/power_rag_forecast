from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def _chat(question: str, session_id: str | None = None) -> dict:
    payload = {"question": question, "debug": True}
    if session_id:
        payload["session_id"] = session_id
    response = client.post("/api/ai/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["answer"]
    assert data["trace"]["guard_result"] in {"passed", "rewritten"}
    return data


def test_weather_data_latest_time_answer():
    data = _chat("天气数据截止的日期")
    assert data["intent"] == "weather_data_latest_time"
    assert data["tools"][0]["name"] == "get_data_freshness"
    assert "最新时间" in data["answer"]
    assert "数据范围" in data["answer"]
    assert "weather_observations" in data["answer"]
    assert "raw_weather" not in data["answer"]


def test_current_date_query_answer():
    data = _chat("今天是几号")
    assert data["intent"] == "current_date_query"
    assert data["tools"][0]["name"] == "get_current_date_context"
    assert "当前日期" in data["answer"]
    assert "不需要调用电力预测数据" not in data["answer"]


def test_storage_discharge_has_multiple_windows():
    data = _chat("哪些时段适合储能放电？")
    assert data["intent"] == "storage_discharge_advice"
    assert data["tools"][0]["name"] == "get_storage_discharge_windows"
    output = data["tool_calls"][0]["output"]
    assert len(output["recommended_discharge_hours"]) >= 3
    assert "低价充电参考" in data["answer"]
    assert "峰谷价差" in data["answer"]


def test_followup_reason_uses_previous_low_price_context():
    first = _chat("明天最低电价是什么时候？", session_id="test_followup_low")
    assert first["intent"] == "forecast_min_price"
    second = _chat("为什么", session_id=first["session_id"])
    assert second["intent"] == "low_price_reason"
    assert "低价窗口" in second["answer"]
    assert "原因" in second["answer"] or "依据" in second["answer"]


def test_user_provided_report_text_is_explained():
    question = (
        "本次运行专属电价智能分析报告基于运行ID 20260528_163940生成，"
        "数据窗口为2024-05-28 00:00:00至2026-05-25 23:00:00，"
        "预测窗口为2026-05-26 00:00:00至2026-05-26 23:00:00。"
        "未来24小时均价为61.9582 USD/MWh，最高价194.0627 USD/MWh出现在17:00，"
        "最低价-26.9293 USD/MWh出现在06:00，峰谷价差达220.9920 USD/MWh。"
        "模型采用高峰增强融合模型，测试集RMSE为13.6538，MAE为7.4830，R2为0.8835。帮我解答"
    )
    data = _chat(question)
    assert data["intent"] == "user_provided_text_explain"
    assert data["tools"][0]["name"] == "explain_user_provided_text"
    for keyword in ["预测窗口", "最高价", "最低价", "峰谷价差"]:
        assert keyword in data["answer"]

from __future__ import annotations

import uuid

from backend.app.ai_assistant.service import answer_chat_accurate


def test_capability_question_returns_product_capabilities() -> None:
    payload = answer_chat_accurate(
        "你可以帮我分析什么？",
        session_id=f"test_capability_{uuid.uuid4().hex}",
        debug=True,
    )

    answer = payload["answer"]
    assert payload["intent"] == "capability"
    assert payload["model_provider_used"] == "deterministic"
    assert payload["llm_used"] is False
    assert "电价走势" in answer
    assert "负荷和天气影响" in answer
    assert "尖峰风险" in answer
    assert "模型误差" in answer
    assert "储能策略" in answer
    assert "报告内容" in answer
    assert payload["timings_ms"]["rag_total_ms"] == 0.0
    assert payload["timings_ms"]["llm_generate_ms"] == 0.0


def test_plain_language_identity_is_deterministic() -> None:
    payload = answer_chat_accurate(
        "用通俗话解释一下你是什么助手",
        session_id=f"test_identity_{uuid.uuid4().hex}",
        debug=True,
    )

    assert payload["intent"] in {"plain_language_intro", "identity", "multi_daily_chat"}
    assert payload["model_provider_used"] == "deterministic"
    assert payload["llm_used"] is False
    assert "懂电价预测和售电交易" in payload["answer"]
    assert "Trace" not in payload["answer"]
    assert "workflow" not in payload["answer"]

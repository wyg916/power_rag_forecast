from __future__ import annotations

import uuid

from backend.app.ai_assistant.service import answer_chat_accurate


def test_one_sentence_capability_fast_path_no_rag_or_llm() -> None:
    payload = answer_chat_accurate(
        "一句话回答：你能做什么？",
        session_id=f"test_daily_{uuid.uuid4().hex}",
        debug=True,
    )

    assert payload["intent"] == "capability"
    assert payload["model_provider_used"] == "deterministic"
    assert payload["llm_used"] is False
    assert payload["tools"] == []
    assert payload["rag_trigger"]["reason"] == "daily_fast_path"
    assert "我会尽量" not in payload["answer"]
    assert "电价预测" in payload["answer"]
    assert "负荷天气" in payload["answer"]
    assert payload["timings_ms"]["llm_generate_ms"] == 0.0
    assert payload["timings_ms"]["rag_total_ms"] == 0.0
    assert payload["timings_ms"]["total_ms"] < 1500


def test_multi_daily_chat_answers_all_parts() -> None:
    payload = answer_chat_accurate(
        "你好 谢谢 你是谁？ 现在几点？ 今天星期几？ 一句话说说你能做什么 你可以帮我分析哪些内容？",
        session_id=f"test_multi_daily_{uuid.uuid4().hex}",
        debug=True,
    )

    answer = payload["answer"]
    assert payload["intent"] == "multi_daily_chat"
    assert payload["model_provider_used"] == "deterministic"
    assert payload["llm_used"] is False
    assert "我是一个面向售电交易和电价预测的智能分析助手" in answer
    assert "现在是" in answer
    assert "星期" in answer
    assert "电价预测" in answer
    assert "模型误差" in answer
    assert payload["rag_trigger"]["reason"] == "daily_fast_path"


def test_time_question_is_lightweight_and_hides_debug_by_default() -> None:
    payload = answer_chat_accurate(
        "现在几点？",
        session_id=f"test_time_{uuid.uuid4().hex}",
        debug=False,
    )

    assert payload["model_provider_used"] == "deterministic"
    assert payload["llm_used"] is False
    assert payload["evidence_summary"] == []
    assert payload["knowledge_evidence_summary"] == []
    assert "现在是" in payload["answer"]
    assert "星期" in payload["answer"]
    assert "运行 ID" not in payload["answer"]
    assert "数据依据" not in payload["answer"]
    assert "知识依据" not in payload["answer"]
    for hidden_key in ["intent", "tools", "tool_calls", "trace", "workflow", "agent_trace"]:
        assert hidden_key not in payload
    assert payload["trace_id"].startswith("trace_")

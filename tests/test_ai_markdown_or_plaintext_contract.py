from __future__ import annotations

from backend.app.ai_assistant.service import sanitize_answer_for_display


def test_markdown_control_symbols_are_removed() -> None:
    raw = "### 结论\n**晚高峰风险偏高**\n---\n- 建议关注负荷。"
    answer = sanitize_answer_for_display(raw)

    assert "###" not in answer
    assert "**" not in answer
    assert "---" not in answer
    assert "结论" in answer
    assert "晚高峰风险偏高" in answer


def test_answer_removes_evidence_paths_scores_and_debug_terms() -> None:
    raw = (
        "结论：需要关注晚高峰。\n"
        "知识依据：E:\\智能运营分析项目\\knowledge_base\\pjm_lmp_price_mechanism.md (score=0.981)\n"
        "Trace ID: trace_abc123\n"
        "workflow: rag -> llm\n"
        "tools: search\n"
    )
    answer = sanitize_answer_for_display(raw)

    assert "E:\\" not in answer
    assert "score=" not in answer
    assert "Trace ID" not in answer
    assert "workflow" not in answer
    assert "tools" not in answer
    assert "结论" in answer

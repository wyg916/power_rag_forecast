from __future__ import annotations

from backend.app.ai_assistant.service import apply_answer_style_contract, sanitize_answer_for_display
from backend.app.ai_assistant.service import answer_chat_accurate


def test_plain_language_uses_short_readable_lines() -> None:
    answer = apply_answer_style_contract(
        "晚高峰价格容易高，是因为大家用电最集中的时间到了。如果供应不够宽松，价格就容易被推高。运营上不要只看全天平均价。",
        "plain_language",
        "risk_reason",
        "用通俗话解释为什么晚高峰价格可能高？",
    )

    lines = [line for line in answer.splitlines() if line.strip()]
    assert len(lines) <= 7
    assert "###" not in answer
    assert "**" not in answer
    assert "intent" not in answer.lower()


def test_sanitized_answer_does_not_have_very_long_unbroken_paragraph() -> None:
    raw = "结论：" + "晚高峰价格可能偏高。" * 80
    answer = sanitize_answer_for_display(raw)
    assert max(len(line) for line in answer.splitlines()) < 1000


def test_storage_boundary_question_is_not_generic(monkeypatch) -> None:
    monkeypatch.setenv("AI_ASSISTANT_LLM_ENABLED", "0")
    payload = answer_chat_accurate("没有储能 SOC 和容量，能给具体充放电量吗？", debug=False)

    assert "不能给具体充放电量" in payload["answer"]
    assert "SOC" in payload["answer"]
    assert "不等同于交易或调度指令" in payload["answer"]

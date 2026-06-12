from __future__ import annotations

import uuid

from backend.app.ai_assistant.service import answer_chat_accurate


def test_default_chat_answer_hides_debug_and_evidence_paths(monkeypatch) -> None:
    monkeypatch.setenv("AI_ASSISTANT_LLM_ENABLED", "0")
    payload = answer_chat_accurate(
        "PJM 的 LMP 是什么意思？",
        session_id=f"test_no_leak_{uuid.uuid4().hex}",
        answer_style="professional_brief",
        model_provider="auto",
        debug=False,
    )

    answer = payload["answer"]
    assert "E:\\" not in answer
    assert "score=" not in answer
    assert "Trace ID" not in answer
    assert "intent" not in answer
    assert "workflow" not in answer
    assert "tools" not in answer
    assert "trace" not in payload
    assert "tool_calls" not in payload

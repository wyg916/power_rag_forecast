from __future__ import annotations

import pytest

from backend.app.ai_assistant.expert_answer_planner import plan_expert_answer
from backend.app import main as app_main


def test_brief_answers_use_a_bounded_generation_budget() -> None:
    brief = plan_expert_answer("trading_risk_summary", "professional_brief", "deepseek")
    deep = plan_expert_answer("trading_risk_summary", "professional_deep", "deepseek")

    assert brief.task_type == "complex_analysis"
    assert brief.max_tokens == 700
    assert deep.max_tokens == 1200


def test_opt_in_rag_prewarm_admits_only_non_fallback_expected_dimension(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setenv("RAG_PREWARM_ON_STARTUP", "1")
    monkeypatch.setenv("RAG_EMBEDDING_EXPECTED_DIM", "3")
    monkeypatch.setattr(
        "backend.app.services.embedding_service.embed_text_with_metadata",
        lambda _: {"embedding": [0.1, 0.2, 0.3], "metadata": {"fallback": False, "error": ""}},
    )
    monkeypatch.setattr(
        "backend.app.services.rerank_service.prewarm_reranker",
        lambda: calls.append("reranker"),
    )

    app_main.prewarm_rag_runtime_if_configured()

    assert calls == ["reranker"]


def test_opt_in_rag_prewarm_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("RAG_PREWARM_ON_STARTUP", "1")
    monkeypatch.setenv("RAG_EMBEDDING_EXPECTED_DIM", "3")
    monkeypatch.setattr(
        "backend.app.services.embedding_service.embed_text_with_metadata",
        lambda _: {"embedding": [0.1], "metadata": {"fallback": True}},
    )

    with pytest.raises(RuntimeError, match="prewarm failed"):
        app_main.prewarm_rag_runtime_if_configured()

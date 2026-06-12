from __future__ import annotations

import pytest

from backend.app.services.rag_service import rag_search


def _title(item: dict) -> str:
    return str(item.get("title") or item.get("source") or "")


def test_policy_document_does_not_outrank_lmp_pjm_terms() -> None:
    result = rag_search("PJM 的 LMP 是什么意思？", top_k=5)
    items = result.get("items") or []
    if not items:
        pytest.skip("RAG knowledge base is not available in this environment")

    titles = [_title(item).lower() for item in items]
    assert "ai_assistant_explanation_policies" not in titles[0]
    assert any(("lmp" in title or "pjm" in title) for title in titles[:3])


def test_policy_document_can_still_answer_boundary_questions() -> None:
    result = rag_search("没有模型误差数据，能判断模型最近变差了吗？没有储能 SOC 和容量，能给具体充放电量吗？", top_k=5)
    items = result.get("items") or []
    if not items:
        pytest.skip("RAG knowledge base is not available in this environment")

    joined = " ".join(_title(item).lower() for item in items[:5])
    assert any(term in joined for term in ["data", "insufficient", "storage", "policy", "ai_assistant", "模型", "储能"])

from __future__ import annotations

from types import SimpleNamespace

from backend.app.repositories.knowledge_repository import build_qa_answer
from backend.app.services import embedding_service, rag_service
from knowledge_pipeline.import_chunks_to_kb import (
    assign_document_identities,
    build_chunk_record,
    evidence_source_type,
    select_curated_rows,
)
from tests.evaluation.run_phase5_rag_acceptance import _forbidden_claim_asserted


def test_embedding_failure_is_fail_closed_without_fallback(monkeypatch):
    class BrokenProvider:
        name = "broken"
        model = "broken-model"
        version = "v1"

        def embed(self, text):
            raise RuntimeError("provider offline")

        def embed_batch(self, texts):
            raise RuntimeError("provider offline")

    monkeypatch.setattr(embedding_service, "get_embedding_provider", lambda: BrokenProvider())
    monkeypatch.setenv("RAG_EMBEDDING_ALLOW_FALLBACK", "0")

    result = embedding_service.embed_text_with_metadata("测试")

    assert result["embedding"] == []
    assert result["metadata"]["fallback"] is False
    assert result["metadata"]["error"] == "RuntimeError"


def test_embedding_dimension_mismatch_is_fail_closed(monkeypatch):
    provider = SimpleNamespace(
        name="sentence_transformers",
        model="bge-large-zh-v1.5",
        version="v1",
        embed=lambda text: [0.1, 0.2],
    )
    monkeypatch.setattr(embedding_service, "get_embedding_provider", lambda: provider)
    monkeypatch.setenv("RAG_EMBEDDING_EXPECTED_DIM", "1024")
    monkeypatch.setenv("RAG_EMBEDDING_ALLOW_FALLBACK", "0")

    result = embedding_service.embed_text_with_metadata("维度错误")

    assert result["embedding"] == []
    assert "embedding_dimension_mismatch" in result["metadata"]["error"]


def test_grounded_answer_quotes_real_chunk():
    result = build_qa_answer(
        "LMP 是什么？",
        {
            "items": [
                {
                    "chunk_id": "chunk_1",
                    "doc_id": "doc_1",
                    "title": "PJM LMP 机制",
                    "section_title": "定义",
                    "source": "knowledge_base/pjm_lmp.md",
                    "content": "LMP 由能源、拥堵和损耗三个价格分量构成。",
                    "domain": "electricity_market",
                    "evidence_source_type": "real",
                    "final_score": 0.88,
                }
            ]
        },
    )

    assert result["available"] is True
    assert result["source_type"] == "real"
    assert result["citations"][0]["chunk_id"] == "chunk_1"
    assert result["citations"][0]["quote"] in "LMP 由能源、拥堵和损耗三个价格分量构成。"


def test_answer_without_evidence_is_unavailable():
    result = build_qa_answer("不存在的内部规则是什么？", {"items": []})

    assert result["available"] is False
    assert result["source_type"] == "unavailable"
    assert result["citations"] == []
    assert "无法据此回答" in result["answer"]


def test_rag_threshold_removes_low_score_items(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "1")
    monkeypatch.setenv("RAG_SCORE_THRESHOLD", "0.7")
    monkeypatch.setenv("RAG_CACHE_ENABLED", "0")
    monkeypatch.setattr(
        rag_service,
        "search_keyword_chunks",
        lambda query, top_k=20: [
            {
                "chunk_id": "low",
                "doc_id": "doc",
                "title": "低分",
                "source": "x",
                "content": "弱相关",
                "keyword_score": 1.0,
                "domain": "electricity_market",
                "evidence_source_type": "real",
            }
        ],
    )
    monkeypatch.setattr(
        rag_service,
        "_vector_search",
        lambda query, top_k, **kwargs: ([], False, {"provider": "disabled", "dim": 0}),
    )
    monkeypatch.setattr(
        rag_service,
        "rerank_candidates",
        lambda query, candidates: ([dict(candidates[0], final_score=0.4)], "test", ""),
    )
    monkeypatch.setattr(rag_service, "knowledge_stats", lambda: {"documents": 1, "chunks": 1})

    result = rag_service.rag_search("弱相关问题", top_k=5)

    assert result["available"] is False
    assert result["items"] == []
    assert result["source_type"] == "unavailable"


def test_curated_selection_removes_short_and_duplicate_chunks():
    rows = [
        {
            "chunk_id": f"c{index}",
            "source_file": f"d{index}.md",
            "source_path": f"knowledge/d{index}.md",
            "title": f"文档{index}",
            "category": "电力市场规则" if index % 2 else "模型与预测方法",
            "chunk_index": 1,
            "text": ("有效知识内容。" * 30) if index != 1 else "过短",
            "text_hash": "same" if index in {2, 3} else f"h{index}",
        }
        for index in range(8)
    ]
    assign_document_identities(rows)

    selected, stats = select_curated_rows(rows, target_chunks=5, min_chars=120, max_chars=1600)

    assert len(selected) == 5
    assert stats["too_short"] == 1
    assert stats["duplicate_content"] == 1
    assert all(row.get("_doc_id") and row.get("_document_version") for row in selected)


def test_pending_import_record_does_not_generate_embedding(tmp_path):
    row = {
        "chunk_id": "source_1",
        "source_file": "2026规则.md",
        "source_path": "knowledge/2026规则.md",
        "title": "2026年电力市场规则",
        "category": "电力市场规则",
        "chunk_index": 1,
        "chunk_total": 1,
        "text": "电力市场规则正文。" * 20,
        "text_hash": "a" * 64,
    }
    assign_document_identities([row])

    record = build_chunk_record(row, [], {}, "test_batch", tmp_path / "chunks.jsonl")

    assert record["embedding"] is None
    assert record["metadata"]["embedding_status"] == "pending"
    assert record["metadata"]["embedding_version"] == ""


def test_content_change_creates_new_document_and_chunk_identity():
    first = {
        "source_path": "knowledge/rule.md",
        "text": "第一版规则内容",
        "text_hash": "1" * 64,
        "chunk_index": 1,
    }
    second = {**first, "text": "第二版规则内容", "text_hash": "2" * 64}
    assign_document_identities([first])
    assign_document_identities([second])

    assert first["_doc_id"] != second["_doc_id"]
    assert first["_db_chunk_id"] != second["_db_chunk_id"]


def test_public_older_year_is_historical_and_project_analysis_is_derived():
    assert evidence_source_type({"title": "2025年电力市场报告"}) == "historical"
    assert evidence_source_type({"title": "AI-项目进展与分析"}) == "derived"


def test_forbidden_claim_detection_respects_explicit_negation():
    claim = "直接等同于可实现收益"

    assert _forbidden_claim_asserted(claim, "峰谷价差可以直接等同于可实现收益") is True
    assert _forbidden_claim_asserted(claim, "峰谷价差不能直接等同于可实现收益") is False

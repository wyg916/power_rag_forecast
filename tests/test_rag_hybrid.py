from __future__ import annotations

from pathlib import Path

from backend.app.services.embedding_service import cosine_similarity, embed_text
from backend.app.services import rag_service


def test_local_embedding_is_nonempty_and_stable(monkeypatch):
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("RAG_EMBEDDING_DIM", "64")

    left = embed_text("晚高峰电价尖峰风险")
    right = embed_text("晚高峰电价尖峰风险")
    other = embed_text("模型误差回填")

    assert left
    assert left == right
    assert cosine_similarity(left, right) > cosine_similarity(left, other)


def test_rag_search_merges_keyword_vector_and_reranks(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "1")
    monkeypatch.setenv("RAG_RERANK_ENABLED", "1")
    monkeypatch.setenv("RAG_RERANK_PROVIDER", "local")
    monkeypatch.setattr(
        rag_service,
        "search_keyword_chunks",
        lambda query, top_k=20: [
            {
                "chunk_id": "chunk_keyword",
                "doc_id": "doc_keyword",
                "title": "尖峰风险解释",
                "source": "knowledge_base/peak.md",
                "content": "尖峰概率高表示需要重点监控，不代表价格一定暴涨。",
                "keyword_score": 3.0,
                "vector_score": 0.0,
            }
        ],
    )
    monkeypatch.setattr(
        rag_service,
        "embed_text_with_metadata",
        lambda text: {"embedding": [1.0, 0.0], "metadata": {"provider": "test", "model": "test", "dim": 2}},
    )
    monkeypatch.setattr(
        rag_service,
        "list_embedded_chunks",
        lambda limit=3000: [
            {
                "chunk_id": "chunk_vector",
                "doc_id": "doc_vector",
                "title": "负荷天气关系",
                "source": "knowledge_base/load_weather.md",
                "content": "负荷预测偏高通常会抬高边际供电压力。",
                "embedding": [1.0, 0.0],
                "keyword_score": 0.0,
                "vector_score": 0.0,
            }
        ],
    )
    monkeypatch.setattr(rag_service, "knowledge_stats", lambda: {"available": True, "documents": 2, "chunks": 2})

    result = rag_service.rag_search("尖峰概率高是不是一定代表价格会暴涨", top_k=2)

    assert result["available"] is True
    assert result["retrieval"]["mode"] == "hybrid"
    assert result["retrieval"]["keyword_candidates"] == 1
    assert result["retrieval"]["vector_candidates"] == 1
    assert len(result["items"]) == 2
    assert all("final_score" in item for item in result["items"])


def test_index_local_knowledge_reads_nested_markdown(monkeypatch, tmp_path):
    root = tmp_path / "knowledge_base"
    nested = root / "price_forecast"
    nested.mkdir(parents=True)
    doc = nested / "peak_spike_risk_explanation.md"
    doc.write_text("# 尖峰风险解释\n\n适用问题示例：尖峰概率高是什么意思？", encoding="utf-8")
    calls: list[dict] = []

    def fake_upsert_document(**kwargs):
        calls.append(kwargs)
        return {"available": True, "doc_id": "fake", "chunks": 1}

    monkeypatch.setattr(rag_service, "SEARCH_ROOTS", [root])
    monkeypatch.setattr(rag_service, "upsert_document", fake_upsert_document)
    monkeypatch.setattr(rag_service, "index_policy_rows", lambda: 0)
    monkeypatch.setattr(rag_service, "knowledge_stats", lambda: {"available": True, "documents": 1, "chunks": 1})

    result = rag_service.index_local_knowledge()

    assert result["indexed_documents"] == 1
    assert calls[0]["title"] == "peak_spike_risk_explanation"
    assert Path(calls[0]["source_path"]).name == "peak_spike_risk_explanation.md"

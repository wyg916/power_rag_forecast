from __future__ import annotations

from copy import deepcopy
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import assistant as assistant_endpoint
from backend.app.api.v1.endpoints import knowledge as knowledge_endpoint
from backend.app.main import app
from backend.app.repositories.knowledge_repository import (
    KNOWLEDGE_STATUSES,
    _document_metadata,
    _normalized_chunk_metadata,
    _retrieval_filter_sql,
    build_qa_answer,
    checksum,
    chunk_id,
    document_id,
    split_chunks,
)
from backend.app.services import embedding_service, rag_service

REAL_ITEM = {
    "chunk_id": "chunk_real_1",
    "doc_id": "doc_real_1",
    "title": "Market Rule",
    "section_title": "Constraints",
    "source": "knowledge/rule.md",
    "source_path": "knowledge/rule.md",
    "source_uri": "kb://rule",
    "content": "Spot trading must verify load forecasts, contracts, and risk limits.",
    "domain": "electricity_market",
    "evidence_source_type": "real",
    "evidence_level": "documented",
    "keyword_score": 1.0,
    "vector_score": 0.8,
    "final_score": 0.9,
    "score": 0.9,
}


def test_document_identity_is_stable_and_versioned():
    content = "Formal knowledge for one version."
    first = document_id("knowledge/rule.md", content, "v1")
    assert first == document_id("knowledge/rule.md", content, "v1")
    assert first != document_id("knowledge/rule.md", content, "v2")
    assert first != document_id("knowledge/rule.md", content + " revised", "v1")


def test_chunk_identity_and_content_hash_are_stable():
    content = "Verifiable knowledge chunk."
    assert chunk_id("doc_1", content) == chunk_id("doc_1", content)
    assert chunk_id("doc_1", content) != chunk_id("doc_1", content + " revised")
    assert chunk_id("doc_1", content).endswith(checksum(content)[:16])


def test_duplicate_document_identity_is_idempotent():
    values = [document_id("knowledge/rule.md", "body", "v1") for _ in range(3)]
    assert len(set(values)) == 1


def test_duplicate_chunks_are_removed_by_content_hash():
    duplicate = "A sufficiently long duplicate knowledge chunk for deduplication."
    assert split_chunks(f"{duplicate}\n\n{duplicate}", chunk_size=20) == [duplicate]


def test_document_contract_contains_required_fields_and_statuses():
    metadata = _document_metadata(
        title="Rule", source_type="knowledge_pipeline_jsonl", source_path="knowledge/rule.md",
        content="Formal rule body.",
        metadata={"domain": "electricity_market", "evidence_source_type": "real", "status": "active"},
    )
    contract = {"document_id": document_id("knowledge/rule.md", "Formal rule body.", metadata["document_version"]), **metadata}
    required = {
        "document_id", "document_version", "title", "domain", "source_type", "source_name",
        "source_uri", "source_path", "effective_at", "expires_at", "generated_at", "content_hash",
        "language", "status", "tags", "evidence_level",
    }
    assert required <= contract.keys()
    assert KNOWLEDGE_STATUSES == {"draft", "active", "superseded", "archived", "invalid"}
    assert contract["source_type"] == "real"


def test_invalid_document_status_is_fail_closed():
    metadata = _document_metadata(
        title="Rule", source_type="jsonl", source_path="rule.md", content="body",
        metadata={"domain": "electricity_market", "status": "unknown"},
    )
    assert metadata["status"] == "invalid"


def test_chunk_contract_contains_required_fields():
    doc_metadata = _document_metadata(
        title="Rule", source_type="jsonl", source_path="rule.md", content="body",
        metadata={"domain": "electricity_market", "evidence_source_type": "real"},
    )
    doc_metadata["document_id"] = "doc_1"
    metadata = _normalized_chunk_metadata(
        document_metadata=doc_metadata, chunk="chunk body", chunk_index=0, embedding_meta=None,
    )
    contract = {"chunk_id": chunk_id("doc_1", "chunk body"), "content": "chunk body", **metadata}
    required = {
        "chunk_id", "document_id", "chunk_index", "section_title", "content", "content_hash",
        "token_count", "domain", "source_type", "embedding_status", "embedding_version",
    }
    assert required <= contract.keys()
    assert contract["embedding_status"] == "pending"


def test_source_type_filter_contract():
    sql, params = _retrieval_filter_sql(source_types=["real"])
    assert "evidence_source_type" in sql
    assert "IN (:source_filter_0)" in sql
    assert params["source_filter_0"] == "real"


def test_domain_filter_contract():
    sql, params = _retrieval_filter_sql(domain="electricity_market")
    assert "d.metadata_json->>'domain' = :domain_filter" in sql
    assert params["domain_filter"] == "electricity_market"


def test_status_and_metadata_conflicts_are_fail_closed_in_sql():
    sql, _ = _retrieval_filter_sql()
    assert "d.metadata_json->>'status'" in sql
    assert "c.metadata_json->>'status'" in sql
    assert "c.metadata_json->>'domain'" in sql
    assert "c.metadata_json->>'source_type'" in sql


def test_demo_historical_and_fallback_are_excluded_by_default():
    _, params = _retrieval_filter_sql()
    assert {"demo", "historical", "fallback"} <= set(params.values())


def test_explicit_demo_and_historical_source_types_are_labeled():
    _, params = _retrieval_filter_sql(source_types=["demo", "historical"])
    citations = rag_service._citations_from_items([
        dict(REAL_ITEM, evidence_source_type="demo"),
        dict(REAL_ITEM, chunk_id="chunk_h", evidence_source_type="historical"),
    ])
    assert set(params.values()) == {"demo", "historical"}
    assert {item["source_type"] for item in citations} == {"demo", "historical"}


def test_hybrid_retrieval_deduplicates_and_orders_by_fused_score():
    keyword = [
        dict(REAL_ITEM, chunk_id="a", keyword_score=10.0, vector_score=0.0),
        dict(REAL_ITEM, chunk_id="b", keyword_score=5.0, vector_score=0.0),
    ]
    vector = [
        dict(REAL_ITEM, chunk_id="b", keyword_score=0.0, vector_score=0.9),
        dict(REAL_ITEM, chunk_id="c", keyword_score=0.0, vector_score=0.8),
    ]
    result = rag_service._merge_candidates(keyword, vector)
    assert [item["chunk_id"] for item in result] == ["b", "c", "a"]
    assert [item["hybrid_score"] for item in result] == sorted((item["hybrid_score"] for item in result), reverse=True)
    assert len({item["chunk_id"] for item in result}) == len(result)


def test_keyword_only_search_applies_threshold_without_embedding(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "0")
    monkeypatch.setenv("RAG_CACHE_ENABLED", "0")
    monkeypatch.setenv("RAG_SCORE_THRESHOLD", "0.5")
    monkeypatch.setattr(
        rag_service, "search_keyword_chunks",
        lambda query, top_k=5, **kwargs: [
            dict(REAL_ITEM, chunk_id="high", keyword_score=10.0),
            dict(REAL_ITEM, chunk_id="low", keyword_score=1.0),
        ],
    )
    monkeypatch.setattr(rag_service, "knowledge_stats", lambda: {"documents": 1, "chunks": 2})
    monkeypatch.setattr(
        rag_service, "embed_text_with_metadata",
        lambda text: (_ for _ in ()).throw(AssertionError("read path generated an embedding")),
    )
    result = rag_service.rag_search("rule", top_k=5)
    assert [item["chunk_id"] for item in result["items"]] == ["high"]
    assert result["retrieval"]["score_threshold"] == 0.5
    assert result["citations"][0]["chunk_id"] == "high"
    assert result["items"][0]["document_id"] == REAL_ITEM["doc_id"]


def test_citation_chunk_and_quote_are_verifiable():
    citations = rag_service._citations_from_items([dict(REAL_ITEM)])
    assert citations[0]["chunk_id"] == REAL_ITEM["chunk_id"]
    assert citations[0]["document_id"] == REAL_ITEM["doc_id"]
    assert citations[0]["quote"] in REAL_ITEM["content"]


def test_grounded_answer_uses_only_real_chunk_quote():
    result = build_qa_answer("What are the constraints?", {"items": [dict(REAL_ITEM)]})
    assert result["available"] is True
    assert result["citations"][0]["quote"] in REAL_ITEM["content"]
    assert result["domain"] == "electricity_market"


def test_missing_or_conflicting_domain_is_unavailable():
    missing = build_qa_answer("rule", {"items": [dict(REAL_ITEM, domain="")]})
    conflict = build_qa_answer(
        "rule", {"items": [dict(REAL_ITEM), dict(REAL_ITEM, chunk_id="chunk_2", domain="forecasting")]},
    )
    assert missing["available"] is False
    assert conflict["available"] is False
    assert missing["source_type"] == conflict["source_type"] == "unavailable"


def test_no_evidence_returns_unavailable_without_fabrication():
    result = build_qa_answer("unknown project fact", {"items": []})
    assert result["available"] is False
    assert result["citations"] == result["evidence"] == []
    assert result["source_type"] == "unavailable"


def test_default_search_call_keeps_legacy_signature(monkeypatch):
    calls = []
    monkeypatch.setattr(
        knowledge_endpoint, "rag_search",
        lambda query, top_k=5: calls.append((query, top_k)) or {"items": []},
    )
    assert knowledge_endpoint._run_search("rule", 5, {"domain": "", "source_types": []}) == {"items": []}
    assert calls == [("rule", 5)]


def test_six_read_paths_100_times_have_no_side_effects(monkeypatch):
    client = TestClient(app)
    headers = {"X-User": "analyst1", "X-Role": "analyst"}
    knowledge_state = {
        "documents": ({"document_id": "doc_real_1", "title": "Market Rule"},),
        "chunks": (deepcopy(REAL_ITEM),), "embeddings_generated": 0, "seeded": 0, "writes": 0,
    }
    before = deepcopy(knowledge_state)
    search_result = {
        "available": True, "source_type": "real", "domain": "electricity_market",
        "items": [deepcopy(REAL_ITEM)],
        "citations": rag_service._citations_from_items([deepcopy(REAL_ITEM)]),
        "retrieval": {"mode": "hybrid"},
    }

    def forbidden_write(*args, **kwargs):
        raise AssertionError("read path attempted a write")

    monkeypatch.setattr(
        knowledge_endpoint, "list_knowledge_documents",
        lambda page=1, page_size=20, search="": {"available": True, "items": list(knowledge_state["documents"]), "total": 1},
    )
    monkeypatch.setattr(
        knowledge_endpoint, "get_knowledge_document",
        lambda doc_id: {"available": True, "document": deepcopy(knowledge_state["documents"][0])},
    )
    monkeypatch.setattr(
        knowledge_endpoint, "list_knowledge_chunks",
        lambda doc_id, page=1, page_size=50: {"available": True, "items": [deepcopy(REAL_ITEM)], "total": 1},
    )
    monkeypatch.setattr(
        knowledge_endpoint, "get_knowledge_citation",
        lambda chunk_id: {"available": True, "citation": deepcopy(search_result["citations"][0])},
    )
    monkeypatch.setattr(knowledge_endpoint, "rag_search", lambda query, top_k=5: deepcopy(search_result))
    monkeypatch.setattr(assistant_endpoint, "rag_search", lambda query, top_k=5, **kwargs: deepcopy(search_result))
    monkeypatch.setattr(knowledge_endpoint, "ensure_seed_knowledge", forbidden_write)
    monkeypatch.setattr(knowledge_endpoint, "upsert_document", forbidden_write)
    monkeypatch.setattr(knowledge_endpoint, "record_search_result", forbidden_write)
    monkeypatch.setattr(embedding_service, "embed_text_with_metadata", forbidden_write)
    monkeypatch.setattr(embedding_service, "embed_batch_with_metadata", forbidden_write)

    requests = (
        ("get", "/api/knowledge/documents", None),
        ("get", "/api/knowledge/documents/doc_real_1", None),
        ("get", "/api/knowledge/documents/doc_real_1/chunks", None),
        ("get", "/api/knowledge/search?q=rule", None),
        ("post", "/api/ai/rag-answer", {"question": "What are the constraints?"}),
        ("get", "/api/knowledge/citations/chunk_real_1", None),
    )
    for method, path, payload in requests:
        for _ in range(100):
            response = client.request(method, path, headers=headers, json=payload)
            assert response.status_code == 200
    assert knowledge_state == before


def test_retrieval_domain_guard_is_fail_closed():
    assert rag_service._domain_consistent_items([dict(REAL_ITEM, domain="")]) == []
    assert rag_service._domain_consistent_items([
        dict(REAL_ITEM), dict(REAL_ITEM, chunk_id="chunk_2", domain="forecasting")
    ]) == []
    assert rag_service._domain_consistent_items([dict(REAL_ITEM)])

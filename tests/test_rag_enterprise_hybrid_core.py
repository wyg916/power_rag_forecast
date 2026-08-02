from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from backend.app.services import rag_service, vector_index_service
from backend.app.services.hybrid_retrieval_service import (
    dynamic_k,
    hybrid_retrieve,
    release_aware_cache_key,
    rrf_fuse,
)
from backend.app.services.qdrant_vector_store import QdrantReadOnlyStore
from backend.app.services.rag_runtime_contract import (
    EmbeddingProfile,
    ReleaseIdentity,
    RetrievalContext,
)

VALID_DENSE = [0.25] + [0.0] * 1023


def _profile():
    return EmbeddingProfile(
        provider="sentence_transformers", model="bge-large-zh-v1.5",
        version="bge-v1", expected_version="bge-v1",
        dimensions=1024, expected_dimensions=1024,
        model_path_configured=True, model_path_exists=True,
        model_path_readable=True, fallback_enabled=False,
    )


def _context(**changes):
    values = dict(
        tenant_id="default", user_id="user-1", roles=("viewer",),
        acl_fingerprint="acl-v1", release_id="RAG-R1",
    )
    values.update(changes)
    return RetrievalContext(**values)


def _point(content_hash="a" * 64):
    return {
        "score": 0.9,
        "payload": {
            "tenant_id": "default", "release_id": "RAG-R1",
            "status": "published", "acl_fingerprint": "acl-v1",
            "acl_public": True, "acl_user_ids": [], "acl_roles": [],
            "valid_from": "2026-01-01T00:00:00Z", "valid_to": None,
            "embedding_provider": "sentence_transformers",
            "embedding_model": "bge-large-zh-v1.5",
            "embedding_version": "bge-v1", "embedding_dimension": 1024,
            "chunk_id": "chunk-1", "document_id": "doc-1",
            "version_id": "version-1", "content_hash": content_hash,
            "content": "子块证据", "parent_content": "父级上下文",
            "domain": "power_market", "title": "风险说明",
        },
    }


class FakeTransport:
    def __init__(self, points):
        self.points = points
        self.requests = []

    def query(self, *, collection, request):
        self.requests.append((collection, deepcopy(request)))
        return {"points": deepcopy(self.points)}


def _store(points):
    return QdrantReadOnlyStore(
        FakeTransport(points),
        ReleaseIdentity("RAG-R1", "rag_chunks_RAG-R1", "rag_chunks_current"),
        _profile(),
    )


def test_rrf_is_stable_deduplicates_identity_and_expands_parent_context():
    first = _point()["payload"] | {"score": 0.8}
    duplicate = first | {"chunk_id": "chunk-duplicate", "score": 0.9}
    other = _point("b" * 64)["payload"] | {
        "chunk_id": "chunk-2", "document_id": "doc-2", "score": 0.7,
    }
    candidates = {"sparse": [duplicate, other], "dense": [first, other]}

    fused = rrf_fuse(candidates)

    assert len(fused) == 2
    assert fused[0]["document_id"] == "doc-1"
    assert fused[0]["retrieval_types"] == ["dense", "sparse"]
    assert fused[0]["context_content"] == "父级上下文\n\n子块证据"
    assert fused == rrf_fuse(candidates)


def test_dynamic_k_and_cache_key_include_release_and_permissions():
    store = _store([])
    base = _context()
    key = release_aware_cache_key(
        context=base, store=store, query="风险", structured_filter={}, top_k=5,
    )

    assert dynamic_k("请综合比较全部风险", 3) == 8
    assert dynamic_k("什么是尖峰风险", 5) == 3
    assert key != release_aware_cache_key(
        context=_context(acl_fingerprint="acl-v2"), store=store,
        query="风险", structured_filter={}, top_k=5,
    )
    assert key != release_aware_cache_key(
        context=_context(user_id="user-2"), store=store,
        query="风险", structured_filter={}, top_k=5,
    )
    other_store = QdrantReadOnlyStore(
        FakeTransport([]),
        ReleaseIdentity("RAG-R2", "rag_chunks_RAG-R2", "rag_chunks_current"),
        _profile(),
    )
    assert key != release_aware_cache_key(
        context=_context(release_id="RAG-R2"), store=other_store,
        query="风险", structured_filter={}, top_k=5,
    )


def test_hybrid_core_refuses_when_no_evidence():
    result = hybrid_retrieve(
        store=_store([]), context=_context(), query="没有证据的问题",
        dense_vector=VALID_DENSE, sparse_query={"text": "问题"},
    )

    assert result.available is False
    assert result.reason == "no_evidence"
    assert result.items == []


def test_enterprise_entry_uses_only_injected_store_and_fails_closed(monkeypatch):
    monkeypatch.setenv("RAG_PROFILE", "enterprise")
    release = ReleaseIdentity("RAG-R1", "rag_chunks_RAG-R1", "rag_chunks_current")
    status = SimpleNamespace(issues=(), release=release, embedding=_profile())
    monkeypatch.setattr(rag_service, "runtime_contract_status", lambda: status)
    monkeypatch.setattr(
        rag_service,
        "embed_text_with_metadata",
        lambda _: {
            "embedding": VALID_DENSE,
            "metadata": {
                "provider": "sentence_transformers", "model": "bge-large-zh-v1.5",
                "version": "bge-v1", "fallback": False,
            },
        },
    )
    monkeypatch.setattr(
        rag_service, "rerank_candidates",
        lambda query, items: ([dict(item, final_score=1.0) for item in items], "bge", ""),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("legacy retrieval must not run")

    for name in ("query_vector_index", "list_embedded_chunks", "search_keyword_chunks", "_fallback_file_search", "knowledge_stats"):
        monkeypatch.setattr(rag_service, name, forbidden)

    assert rag_service.rag_search("问题")["retrieval"]["reason"] == "retrieval_context_missing"
    result = rag_service.rag_search(
        "什么是尖峰风险", context=_context(), enterprise_store=_store([_point()]),
        domain="power_market",
    )
    empty = rag_service.rag_search(
        "没有证据", context=_context(), enterprise_store=_store([]),
    )

    assert result["available"] is True
    assert result["retrieval"]["mode"] == "enterprise_qdrant_hybrid"
    assert result["retrieval"]["cache_key"].startswith("rag2:")
    assert empty["available"] is False and empty["retrieval"]["reason"] == "no_evidence"
    assert vector_index_service.query_vector_index([0.0] * 1024)["reason"] == "enterprise_npz_forbidden"

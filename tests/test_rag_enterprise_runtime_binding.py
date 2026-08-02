from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.app.knowledge_enterprise_contracts import (
    EmbeddingProfileContract,
    ReleaseContract,
    ReleaseState,
)
from backend.app.services.qdrant_vector_store import QdrantReadOnlyStore
from backend.app.services.rag_enterprise_runtime import (
    Bm25QueryEncoder,
    EnterpriseRetrievalRuntime,
    QdrantHttpReadOnlyTransport,
)
from backend.app.services.rag_runtime_contract import EmbeddingProfile, ReleaseIdentity


NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)
VALID_DENSE = [0.25] + [0.0] * 1023


def _embedding() -> EmbeddingProfile:
    return EmbeddingProfile(
        provider="sentence_transformers",
        model="baai/bge-large-zh-v1.5",
        version="sha256:" + "a" * 64,
        expected_version="sha256:" + "a" * 64,
        dimensions=1024,
        expected_dimensions=1024,
        model_path_configured=True,
        model_path_exists=True,
        model_path_readable=True,
        fallback_enabled=False,
    )


def _contract():
    return SimpleNamespace(
        issues=(),
        release=ReleaseIdentity(
            "RAG-R1", "rag_chunks_RAG-R1", "rag_chunks_current"
        ),
        embedding=_embedding(),
        qdrant=SimpleNamespace(issues=(), endpoint="https://127.0.0.1:6333"),
    )


def _release() -> ReleaseContract:
    return ReleaseContract(
        release_id="RAG-R1",
        tenant_id="default",
        status=ReleaseState.PUBLISHED,
        collection="rag_chunks_RAG-R1",
        alias="rag_chunks_current",
        manifest_sha256="b" * 64,
        embedding_profile=EmbeddingProfileContract(
            provider="sentence_transformers",
            model="BAAI/bge-large-zh-v1.5",
            version="sha256:" + "a" * 64,
            dimension=1024,
            sparse_profile="bm25-zh-v1",
        ),
        gates=[],
        run_id="run-1",
        trace_id="trace-1",
        created_at=NOW,
        updated_at=NOW,
    )


def _payload(**changes):
    value = {
        "tenant_id": "default",
        "release_id": "RAG-R1",
        "status": "published",
        "acl_fingerprint": "resource-acl",
        "acl_public": True,
        "acl_user_ids": [],
        "acl_roles": [],
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_to": None,
        "embedding_provider": "sentence_transformers",
        "embedding_model": "BAAI/bge-large-zh-v1.5",
        "embedding_version": "sha256:" + "a" * 64,
        "embedding_dimension": 1024,
        "sparse_profile": "bm25-zh-v1",
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "version_id": "version-1",
        "content_hash": "c" * 64,
        "content": "电力市场证据",
        "domain": "power_market",
    }
    value.update(changes)
    return value


class Reader:
    def __init__(self, release):
        self.release = release
        self.calls = 0

    def current_published_release(self, *, tenant_id):
        assert tenant_id == "default"
        self.calls += 1
        return self.release


class ControlPlane:
    def __init__(self, *, alias="rag_chunks_RAG-R1", payload=None):
        self.alias = alias
        self.payload = deepcopy(payload or _payload())
        self.calls = []

    def current_alias(self, alias):
        self.calls.append(("alias", alias))
        return self.alias

    def collection_details(self, collection):
        self.calls.append(("collection", collection))
        return {
            "config": {
                "params": {
                    "vectors": {"dense": {"size": 1024, "distance": "Cosine"}},
                    "sparse_vectors": {"bm25": {"index": {"on_disk": True}}},
                },
                "strict_mode_config": {"enabled": True},
            }
        }

    def sample_payload(self, alias, release_id):
        self.calls.append(("sample", alias, release_id))
        return deepcopy(self.payload)

    def query(self, *, collection, request):
        self.calls.append(("query", collection, deepcopy(request)))
        return {"points": [{"score": 0.9, "payload": deepcopy(self.payload)}]}


def _runtime(reader, transport_factory):
    return EnterpriseRetrievalRuntime(
        release_reader=reader,
        contract_provider=_contract,
        transport_factory=transport_factory,
    )


def test_missing_current_release_stops_before_any_qdrant_access():
    reader = Reader(None)

    def forbidden(_):
        raise AssertionError("Qdrant must not be accessed without a current published release")

    binding = _runtime(reader, forbidden).bind(
        user_id="analyst-1", roles=("analyst",), run_id="run-1", trace_id="trace-1"
    )

    assert binding.available is False
    assert binding.public_reason == "release_unavailable"
    assert binding.diagnostic_reason == "current_published_release_missing"
    assert reader.calls == 1


def test_alias_or_payload_profile_mismatch_fails_closed():
    for control, reason in (
        (ControlPlane(alias=None), "qdrant_alias_mismatch"),
        (ControlPlane(payload=_payload(sparse_profile="other")), "qdrant_payload_profile_mismatch"),
    ):
        binding = _runtime(Reader(_release()), lambda _: control).bind(
            user_id="analyst-1",
            roles=("analyst",),
            run_id="run-1",
            trace_id="trace-1",
        )
        assert binding.available is False
        assert binding.public_reason == "release_unavailable"
        assert binding.diagnostic_reason == reason


def test_consistent_four_way_binding_queries_only_through_alias():
    control = ControlPlane()
    binding = _runtime(Reader(_release()), lambda _: control).bind(
        user_id="analyst-1", roles=("analyst",), run_id="run-1", trace_id="trace-1"
    )

    assert binding.available is True
    assert isinstance(binding.store, QdrantReadOnlyStore)
    result = binding.store.search(
        context=binding.context,
        dense_vector=VALID_DENSE,
        sparse_query=None,
        structured_filter=None,
        limit=5,
        now=NOW,
    )

    assert result.available is True
    query_calls = [call for call in control.calls if call[0] == "query"]
    assert len(query_calls) == 1
    assert query_calls[0][1] == "rag_chunks_current"
    serialized = str(query_calls[0][2]["filter"])
    assert "RAG-R1" in serialized and "bm25-zh-v1" in serialized


def test_bm25_encoder_verifies_profile_hash_and_encodes_known_terms():
    base = {
        "profile": "bm25-zh-v1",
        "tokenizer": "nfkc-lower-cjk-unigram-bigram-alnum/v1",
        "k1": 1.2,
        "b": 0.75,
        "chunk_count": 2,
        "empty_sparse_chunks": 0,
        "average_document_length": 4.0,
        "vocabulary": ["力", "电", "电力"],
        "idf": [0.2, 0.3, 0.4],
    }
    digest = hashlib.sha256(
        json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    encoded = Bm25QueryEncoder({**base, "profile_sha256": digest}).encode("电力")

    assert encoded["indices"] == [1, 2, 3]
    assert all(value > 0 for value in encoded["values"])


def test_http_transport_maps_sparse_and_structured_to_read_only_post_calls():
    transport = object.__new__(QdrantHttpReadOnlyTransport)
    transport._encoder = SimpleNamespace(
        encode=lambda _: {"indices": [7], "values": [0.5]}
    )
    calls = []

    def request(path, *, method="GET", payload=None):
        calls.append((path, method, deepcopy(payload)))
        return {"result": {"points": []}}

    transport._request = request
    base = {
        "filter": {"must": []},
        "limit": 5,
        "with_payload": True,
        "with_vector": False,
    }
    transport.query(
        collection="rag_chunks_current",
        request={**base, "mode": "sparse", "query": {"text": "电力"}},
    )
    transport.query(
        collection="rag_chunks_current",
        request={**base, "mode": "structured", "query": None},
    )

    assert [call[1] for call in calls] == ["POST", "POST"]
    assert calls[0][2]["using"] == "bm25"
    assert calls[0][2]["query"] == {"indices": [7], "values": [0.5]}
    assert calls[1][0].endswith("/points/scroll")

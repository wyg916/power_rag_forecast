from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import Barrier, Lock

import pytest

from backend.app.services.qdrant_vector_store import QdrantReadOnlyStore
from backend.app.services.rag_runtime_contract import (
    EmbeddingProfile,
    ReleaseIdentity,
    RetrievalContext,
)


NOW = datetime(2026, 7, 31, tzinfo=timezone.utc)
VALID_DENSE = [0.25] + [0.0] * 1023


def _profile() -> EmbeddingProfile:
    return EmbeddingProfile(
        provider="sentence_transformers",
        model="bge-large-zh-v1.5",
        version="bge-v1",
        expected_version="bge-v1",
        dimensions=1024,
        expected_dimensions=1024,
        model_path_configured=True,
        model_path_exists=True,
        model_path_readable=True,
        fallback_enabled=False,
    )


def _context(**changes) -> RetrievalContext:
    values = {
        "tenant_id": "default",
        "user_id": "user-1",
        "roles": ("viewer",),
        "acl_fingerprint": "acl-v1",
        "release_id": "RAG-R1",
    }
    values.update(changes)
    return RetrievalContext(**values)


def _payload(**changes):
    value = {
        "tenant_id": "default",
        "release_id": "RAG-R1",
        "status": "published",
        "acl_fingerprint": "acl-v1",
        "acl_public": True,
        "acl_user_ids": [],
        "acl_roles": [],
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_to": None,
        "embedding_provider": "sentence_transformers",
        "embedding_model": "bge-large-zh-v1.5",
        "embedding_version": "bge-v1",
        "embedding_dimension": 1024,
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "version_id": "version-1",
        "content_hash": "a" * 64,
        "content": "子块证据",
        "parent_content": "父级上下文",
        "domain": "power_market",
    }
    value.update(changes)
    return value


class FakeTransport:
    def __init__(self, payload=None):
        self.payload = payload
        self.requests = []
        self.write_count = 0

    def query(self, *, collection, request):
        self.requests.append((collection, deepcopy(request)))
        points = [] if self.payload is None else [{"score": 0.9, "payload": deepcopy(self.payload)}]
        return {"points": points}


class ConcurrentTransport(FakeTransport):
    def __init__(self, payload=None, parties=3):
        super().__init__(payload)
        self.barrier = Barrier(parties, timeout=2)
        self.request_lock = Lock()

    def query(self, *, collection, request):
        with self.request_lock:
            self.requests.append((collection, deepcopy(request)))
        self.barrier.wait()
        points = [] if self.payload is None else [{"score": 0.9, "payload": deepcopy(self.payload)}]
        return {"points": points}


class PartiallyFailingTransport(FakeTransport):
    def __init__(self, payload=None):
        super().__init__(payload)
        self.request_lock = Lock()

    def query(self, *, collection, request):
        with self.request_lock:
            self.requests.append((collection, deepcopy(request)))
        if request["mode"] == "sparse":
            raise RuntimeError("simulated_transport_failure")
        points = [] if self.payload is None else [{"score": 0.9, "payload": deepcopy(self.payload)}]
        return {"points": points}


def _store(transport, release=None):
    return QdrantReadOnlyStore(
        transport,
        release or ReleaseIdentity("RAG-R1", "rag_chunks_RAG-R1", "rag_chunks_current"),
        _profile(),
    )


def test_store_builds_mandatory_filters_and_uses_release_collection_only():
    transport = FakeTransport(_payload())
    original = deepcopy(transport.payload)

    result = _store(transport).search(
        context=_context(),
        dense_vector=VALID_DENSE,
        sparse_query={"text": "尖峰风险"},
        structured_filter={"domain": "power_market"},
        limit=20,
        now=NOW,
    )

    assert result.available is True
    assert set(result.candidates) == {"dense", "sparse", "structured"}
    assert len(transport.requests) == 3
    assert {item[0] for item in transport.requests} == {"rag_chunks_RAG-R1"}
    serialized_filter = str(transport.requests[0][1]["filter"])
    for required in ("tenant_id", "release_id", "published", "valid_from", "acl_roles", "embedding_version"):
        assert required in serialized_filter
    assert "acl_fingerprint" not in serialized_filter
    assert transport.write_count == 0
    assert transport.payload == original
    assert list(result.candidates) == ["dense", "sparse", "structured"]
    assert result.timings_ms["qdrant_wall_ms"] >= 0.0
    assert result.timings_ms["payload_acl_ms"] >= 0.0


def test_store_runs_read_only_modes_concurrently_and_keeps_result_order():
    transport = ConcurrentTransport(_payload())

    result = _store(transport).search(
        context=_context(),
        dense_vector=VALID_DENSE,
        sparse_query={"text": "尖峰风险"},
        structured_filter={"domain": "power_market"},
        limit=20,
        now=NOW,
    )

    assert result.available is True
    assert list(result.candidates) == ["dense", "sparse", "structured"]
    assert result.request_count == 3
    assert {request[1]["mode"] for request in transport.requests} == {
        "dense",
        "sparse",
        "structured",
    }


def test_store_discards_all_candidates_when_any_parallel_mode_fails():
    transport = PartiallyFailingTransport(_payload())

    result = _store(transport).search(
        context=_context(),
        dense_vector=VALID_DENSE,
        sparse_query={"text": "尖峰风险"},
        structured_filter=None,
        limit=20,
        now=NOW,
    )

    assert result.available is False
    assert result.reason == "transport_unavailable"
    assert result.candidates == {}
    assert result.request_count == 2
    assert {request[1]["mode"] for request in transport.requests} == {
        "dense",
        "sparse",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tenant_id", "other"),
        ("release_id", "other"),
        ("status", "draft"),
        ("acl_fingerprint", ""),
        ("embedding_version", "other"),
        ("valid_from", "2027-01-01T00:00:00Z"),
        ("valid_to", "2026-01-01T00:00:00Z"),
    ],
)
def test_store_rejects_payload_contract_violations(field, value):
    transport = FakeTransport(_payload(**{field: value}))

    result = _store(transport).search(
        context=_context(),
        dense_vector=VALID_DENSE,
        sparse_query=None,
        structured_filter=None,
        limit=5,
        now=NOW,
    )

    assert result.available is False
    assert result.reason == "payload_contract_violation"


def test_store_allows_public_resource_fingerprint_but_rejects_acl_denial():
    public = FakeTransport(_payload(acl_fingerprint="resource-acl-v9", acl_public=True))
    assert _store(public).search(
        context=_context(), dense_vector=VALID_DENSE, sparse_query=None,
        structured_filter=None, limit=5, now=NOW,
    ).available is True

    denied = FakeTransport(
        _payload(acl_fingerprint="resource-acl-v9", acl_public=False,
                 acl_user_ids=["other"], acl_roles=["admin"])
    )
    assert _store(denied).search(
        context=_context(), dense_vector=VALID_DENSE, sparse_query=None,
        structured_filter=None, limit=5, now=NOW,
    ).reason == "payload_contract_violation"


@pytest.mark.parametrize(
    "dense_vector",
    ([0.0] * 1024, [float("nan")] + [0.0] * 1023, [float("inf")] + [0.0] * 1023),
)
def test_store_rejects_invalid_dense_vectors(dense_vector):
    transport = FakeTransport(_payload())
    result = _store(transport).search(
        context=_context(), dense_vector=dense_vector, sparse_query=None,
        structured_filter=None, limit=5, now=NOW,
    )
    assert result.reason == "query_embedding_invalid"
    assert transport.requests == []


def test_store_rejects_missing_context_and_arbitrary_collection():

    missing = FakeTransport(_payload())
    assert _store(missing).search(
        context=_context(user_id=""), dense_vector=VALID_DENSE, sparse_query=None,
        structured_filter=None, limit=5, now=NOW,
    ).reason == "user_id_missing"
    assert missing.requests == []

    arbitrary = FakeTransport(_payload())
    bad_release = ReleaseIdentity("RAG-R1", "attacker_collection", "rag_chunks_current")
    assert _store(arbitrary, bad_release).search(
        context=_context(), dense_vector=VALID_DENSE, sparse_query=None,
        structured_filter=None, limit=5, now=NOW,
    ).reason == "release_collection_mismatch"
    assert arbitrary.requests == []

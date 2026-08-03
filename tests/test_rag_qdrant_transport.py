from __future__ import annotations

import inspect
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import pytest
from sqlalchemy import create_engine, text

from backend.app.api.v1.endpoints.knowledge import _search_payload
from backend.app.services import rag_qdrant_transport as module


def _profile() -> dict:
    base = {
        "chunk_count": 8339,
        "vocabulary": {"电": 0, "价": 1, "电价": 2, "risk": 3},
        "idf": [1.0, 2.0, 3.0, 4.0],
    }
    return base | {"profile_sha256": __import__("hashlib").sha256(module._canonical(base)).hexdigest()}


def _immutable_profile() -> dict:
    base = {
        "chunk_count": 8339,
        "vocabulary": ["电", "价", "电价", "risk"],
        "idf": [1.0, 2.0, 3.0, 4.0],
        "k1": 1.2,
        "b": 0.75,
        "average_document_length": 12.0,
    }
    return base | {"profile_sha256": __import__("hashlib").sha256(module._canonical(base)).hexdigest()}


def test_sparse_query_is_stable_and_never_hash_embeds() -> None:
    first = module.sparse_query("电价 risk", _profile())
    second = module.sparse_query("电价 risk", _profile())
    assert first == second
    assert first["indices"] == sorted(first["indices"])
    assert len(first["indices"]) == len(first["values"])
    assert "hash_embedding" not in inspect.getsource(module)


def test_sparse_query_matches_immutable_one_based_bm25_profile() -> None:
    result = module.sparse_query("电价 risk", _immutable_profile())

    assert result["indices"] == [1, 2, 3, 4]
    assert len(result["values"]) == 4
    assert all(value > 0 for value in result["values"])


def test_sparse_query_reuses_only_a_fully_validated_list_lookup() -> None:
    profile = _immutable_profile()
    with module._BM25_LOOKUP_CACHE_LOCK:
        module._BM25_LOOKUP_CACHE.clear()

    first = module.sparse_query("电价 risk", profile)
    second = module.sparse_query("电价 risk", profile)

    assert first == second
    with module._BM25_LOOKUP_CACHE_LOCK:
        assert len(module._BM25_LOOKUP_CACHE) == 1

    invalid = _immutable_profile()
    invalid["vocabulary"] = ["已", "被", "篡改", "risk"]
    with pytest.raises(module.QdrantReadError, match="bm25_profile_invalid"):
        module.sparse_query("risk", invalid)


def test_ssl_context_cache_is_scoped_to_ca_file_signature(monkeypatch) -> None:
    signature = [("E:/runtime/ca.pem", 1, 100)]
    created: list[str] = []

    monkeypatch.setattr(module, "_tls_file_signature", lambda _: signature[0])
    monkeypatch.setattr(
        module.ssl,
        "create_default_context",
        lambda *, cafile: created.append(cafile) or object(),
    )
    with module._SSL_CONTEXT_CACHE_LOCK:
        module._SSL_CONTEXT_CACHE.clear()

    first = module._cached_ssl_context("ignored")
    second = module._cached_ssl_context("ignored")
    signature[0] = ("E:/runtime/ca.pem", 2, 100)
    third = module._cached_ssl_context("ignored")

    assert first is second
    assert third is not first
    assert created == ["E:/runtime/ca.pem", "E:/runtime/ca.pem"]


def test_concurrent_modes_validate_alias_once_per_transport() -> None:
    transport = object.__new__(module.QdrantHttpsReadOnlyTransport)
    transport._alias_lock = Lock()
    transport._alias_checked = False
    transport._alias_error = ""
    transport.bm25 = _immutable_profile()
    alias_calls: list[int] = []
    request_modes: list[str] = []
    request_lock = Lock()

    def current_alias() -> str:
        alias_calls.append(1)
        return "rag_chunks_RAG-R1"

    def request(path, payload):
        with request_lock:
            request_modes.append(str(payload.get("using") or "structured"))
        return {"points": []}

    transport._current_alias = current_alias
    transport._request = request
    requests = (
        {"mode": "dense", "query": [0.25] + [0.0] * 1023},
        {"mode": "sparse", "query": {"text": "电价 risk"}},
        {"mode": "structured", "query": None},
    )

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(
            executor.map(
                lambda value: transport.query(
                    collection="rag_chunks_RAG-R1", request=value
                ),
                requests,
            )
        )

    assert results == [{"points": []}] * 3
    assert len(alias_calls) == 1
    assert set(request_modes) == {"dense", "bm25", "structured"}


def test_client_tenant_override_is_rejected() -> None:
    with pytest.raises(Exception) as error:
        _search_payload({"query": "规则", "tenant_id": "other"})
    assert getattr(error.value, "status_code", None) == 400


def test_transport_is_read_only_and_fixed_to_release_collection() -> None:
    source = inspect.getsource(module.QdrantHttpsReadOnlyTransport)
    assert 'method="POST"' in source
    assert 'method="PUT"' not in source
    assert 'method="DELETE"' not in source
    assert 'collection != "rag_chunks_RAG-R1"' in source
    assert "QDRANT_ADMIN_API_KEY" not in source
    assert 'quote(CURRENT_ALIAS)' in source
    assert "published_alias_mismatch" in source


def test_postgres_current_release_gate_rejects_candidate_and_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE kb_releases (
                  tenant_id TEXT, release_id TEXT, collection_name TEXT,
                  status TEXT, is_current BOOLEAN
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO kb_releases VALUES
                  ('default','RAG-R1','rag_chunks_RAG-R1','candidate',false)
                """
            )
        )
    monkeypatch.setattr(module, "postgres_engine", lambda: engine)

    assert module._postgres_release_is_current("RAG-R1", "rag_chunks_RAG-R1") is False
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE kb_releases SET status='published', is_current=true WHERE release_id='RAG-R1'"
            )
        )
    assert module._postgres_release_is_current("RAG-R1", "rag_chunks_RAG-R1") is True
    assert module._postgres_release_is_current("RAG-R2", "rag_chunks_RAG-R2") is False

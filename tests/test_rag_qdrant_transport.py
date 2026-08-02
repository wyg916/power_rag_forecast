from __future__ import annotations

import inspect

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

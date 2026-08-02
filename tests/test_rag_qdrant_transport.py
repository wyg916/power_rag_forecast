from __future__ import annotations

import inspect

import pytest

from backend.app.api.v1.endpoints.knowledge import _search_payload
from backend.app.services import rag_qdrant_transport as module


def _profile() -> dict:
    base = {
        "chunk_count": 8339,
        "vocabulary": {"电": 0, "价": 1, "电价": 2, "risk": 3},
        "idf": [1.0, 2.0, 3.0, 4.0],
    }
    return base | {"profile_sha256": __import__("hashlib").sha256(module._canonical(base)).hexdigest()}


def test_sparse_query_is_stable_and_never_hash_embeds() -> None:
    first = module.sparse_query("电价 risk", _profile())
    second = module.sparse_query("电价 risk", _profile())
    assert first == second
    assert first["indices"] == sorted(first["indices"])
    assert len(first["indices"]) == len(first["values"])
    assert "hash_embedding" not in inspect.getsource(module)


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

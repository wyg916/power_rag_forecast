from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.services.knowledge_enterprise_service import (
    EnterpriseKnowledgeUnavailable,
)
from backend.app.services.rag_release_api_service import (
    RagReleaseApiService,
    ReleaseWorkerClient,
    _public_release,
)


def test_public_release_excludes_technical_runtime_fields() -> None:
    value = _public_release(
        {
            "release_id": "RAG-R1",
            "status": "candidate",
            "is_current": False,
            "document_count": 45,
            "chunk_count": 8339,
            "isolated_count": 24,
            "duplicate_count": 14,
            "gate_total": 12,
            "gate_passed": 11,
            "created_at": datetime(2026, 8, 2, tzinfo=timezone.utc),
        }
    )

    assert value["release_id"] == "RAG-R1"
    assert value["gates"] == {"passed": 11, "total": 12, "ready": False}
    forbidden = {
        "tenant_id", "collection", "collection_name", "embedding_provider",
        "embedding_model", "embedding_version", "trace_id", "run_id",
    }
    assert forbidden.isdisjoint(value)


@pytest.mark.parametrize(
    "endpoint,allowed",
    [
        ("http://127.0.0.1:8787", True),
        ("http://localhost:8787", True),
        ("https://release-worker.internal", True),
        ("http://release-worker.internal", False),
        ("file:///tmp/worker", False),
    ],
)
def test_worker_transport_accepts_only_https_or_localhost_http(
    monkeypatch: pytest.MonkeyPatch, endpoint: str, allowed: bool
) -> None:
    monkeypatch.setenv("RAG_RELEASE_WORKER_URL", endpoint)
    monkeypatch.setenv("RAG_RELEASE_WORKER_TOKEN", "separated-worker-token")
    if allowed:
        assert ReleaseWorkerClient.from_environment().endpoint == endpoint
    else:
        with pytest.raises(EnterpriseKnowledgeUnavailable, match="transport_rejected"):
            ReleaseWorkerClient.from_environment()


def test_api_service_never_reads_qdrant_admin_key(monkeypatch: pytest.MonkeyPatch) -> None:
    accessed: list[str] = []
    original_get = __import__("os").environ.get

    def guarded_get(key: str, default=None):
        accessed.append(key)
        if "ADMIN" in key:
            raise AssertionError("API runtime attempted to read an admin secret")
        return original_get(key, default)

    monkeypatch.setattr("backend.app.services.rag_release_api_service.os.environ.get", guarded_get)
    monkeypatch.setenv("RAG_RELEASE_WORKER_URL", "http://127.0.0.1:8787")
    monkeypatch.setenv("RAG_RELEASE_WORKER_TOKEN", "separated-worker-token")

    assert ReleaseWorkerClient.from_environment().token == "separated-worker-token"
    assert all("QDRANT" not in key for key in accessed)


def test_worker_not_configured_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAG_RELEASE_WORKER_URL", raising=False)
    monkeypatch.delenv("RAG_RELEASE_WORKER_TOKEN", raising=False)
    with pytest.raises(EnterpriseKnowledgeUnavailable, match="not_configured"):
        ReleaseWorkerClient.from_environment()


def test_unknown_public_status_fails_closed() -> None:
    with pytest.raises(EnterpriseKnowledgeUnavailable, match="status_invalid"):
        _public_release({"release_id": "RAG-R1", "status": "mystery"})


def test_ingestion_read_is_fail_closed_without_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.app.services.rag_release_api_service.postgres_engine", lambda: None
    )
    with pytest.raises(EnterpriseKnowledgeUnavailable, match="postgres_release_store_unavailable"):
        RagReleaseApiService().get_ingestion(tenant_id="default", ingestion_id="source-1")

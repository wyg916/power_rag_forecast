from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import knowledge
from backend.app.core.security import CurrentUser, ROLE_PERMISSIONS, get_current_user
from backend.app.knowledge_enterprise_contracts import (
    EmbeddingProfileContract,
    ReleaseContract,
    ReleaseState,
)
from backend.app.services.rag_enterprise_runtime import EnterpriseRetrievalBinding
from backend.app.services.rag_runtime_contract import RetrievalContext


NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)


def _release(status: ReleaseState = ReleaseState.CANDIDATE) -> ReleaseContract:
    return ReleaseContract(
        release_id="RAG-R1",
        tenant_id="default",
        status=status,
        collection="rag_chunks_RAG-R1",
        alias="rag_chunks_current",
        manifest_sha256="a" * 64,
        embedding_profile=EmbeddingProfileContract(
            provider="sentence_transformers",
            model="BAAI/bge-large-zh-v1.5",
            version="sha256:" + "b" * 64,
            dimension=1024,
            sparse_profile="bm25-zh-v1",
        ),
        gates=[],
        run_id="run-1",
        trace_id="trace-1",
        created_at=NOW,
        updated_at=NOW,
    )


class _Application:
    available = True

    def list_releases(self, **_):
        return [_release()]

    def create_release(self, **_):
        return _release()

    def validate_release(self, **_):
        return _release(ReleaseState.VALIDATED)

    def publish_release(self, **_):
        return _release(ReleaseState.PUBLISHED)

    def rollback_release(self, **_):
        return _release(ReleaseState.ROLLED_BACK)


def _client(role: str) -> TestClient:
    app = FastAPI()
    app.include_router(knowledge.router)
    user = CurrentUser(
        user_id=f"{role}-1",
        username=f"{role}-1",
        role=role,
        permissions=sorted(ROLE_PERMISSIONS[role]),
        auth_mode="test",
    )
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[knowledge.enterprise_knowledge_application] = _Application
    return TestClient(app)


def test_frozen_knowledge_role_permissions() -> None:
    assert "knowledge:read" in ROLE_PERMISSIONS["analyst"]
    assert "knowledge:write" not in ROLE_PERMISSIONS["analyst"]
    assert {"knowledge:read", "knowledge:write", "knowledge:publish"}.issubset(
        ROLE_PERMISSIONS["reviewer"]
    )
    assert "knowledge:diagnose" in ROLE_PERMISSIONS["developer"]
    assert "knowledge:read" not in ROLE_PERMISSIONS["viewer"]


def test_release_list_is_public_business_projection() -> None:
    response = _client("analyst").get("/api/knowledge/releases")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert set(payload["items"][0]) == {
        "release_id", "status", "created_at", "updated_at"
    }
    serialized = str(payload)
    for forbidden in ("collection", "provider", "dimension", "trace_id", "model_path"):
        assert forbidden not in serialized


def test_client_tenant_override_is_rejected() -> None:
    response = _client("analyst").get(
        "/api/knowledge/releases?tenant_id=other", headers={"X-Tenant-ID": "other"}
    )
    assert response.status_code == 400
    body = {
        "release_id": "RAG-R1",
        "source_ledger_sha256": "a" * 64,
        "candidate_manifest_sha256": "b" * 64,
        "embedding_profile": {
            "provider": "sentence_transformers",
            "model": "BAAI/bge-large-zh-v1.5",
            "version": "v1",
            "dimension": 1024,
            "sparse_profile": "bm25-zh-v1",
        },
        "idempotency_key": "candidate-001",
        "tenant_id": "other",
    }
    assert _client("reviewer").post("/api/knowledge/releases", json=body).status_code == 422


def test_publish_actions_are_reviewer_only() -> None:
    assert _client("analyst").post(
        "/api/knowledge/releases/RAG-R1/publish"
    ).status_code == 403
    response = _client("reviewer").post(
        "/api/knowledge/releases/RAG-R1/publish",
        headers={"X-Run-ID": "run-api-1", "X-Trace-ID": "trace-api-1"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "published"


def test_diagnostics_permission_is_separate(monkeypatch) -> None:
    monkeypatch.setattr(
        knowledge, "rag_health", lambda diagnostic=False: {"diagnostics": diagnostic}
    )
    assert _client("analyst").get("/api/knowledge/health/diagnostics").status_code == 403
    response = _client("developer").get("/api/knowledge/health/diagnostics")
    assert response.status_code == 200
    assert response.json() == {"diagnostics": True}


def test_enterprise_search_binds_server_auth_context_and_safe_failure(monkeypatch) -> None:
    captured = {}

    class Runtime:
        def bind(self, **kwargs):
            captured["binding"] = kwargs
            return EnterpriseRetrievalBinding(
                context=RetrievalContext(
                    tenant_id="default",
                    user_id=kwargs["user_id"],
                    roles=kwargs["roles"],
                    acl_fingerprint="acl-v1",
                    release_id="RAG-R1",
                    run_id=kwargs["run_id"],
                    trace_id=kwargs["trace_id"],
                ),
                store=None,
                public_reason="release_unavailable",
                diagnostic_reason="current_published_release_missing",
            )

    def search(query, top_k=5, **kwargs):
        captured["search"] = {"query": query, "top_k": top_k, **kwargs}
        return {
            "available": False,
            "items": [],
            "citations": [],
            "retrieval": {"reason": kwargs["enterprise_unavailable_reason"]},
        }

    runtime = Runtime()
    monkeypatch.setattr(knowledge, "enterprise_mode", lambda: True)
    monkeypatch.setattr(knowledge, "enterprise_retrieval_runtime", lambda: runtime)
    monkeypatch.setattr(knowledge, "rag_search", search)
    response = _client("analyst").get(
        "/api/knowledge/search?q=peak",
        headers={"X-Run-ID": "run-api-1", "X-Trace-ID": "trace-api-1"},
    )

    assert response.status_code == 200
    assert response.json()["retrieval"]["reason"] == "release_unavailable"
    assert captured["binding"] == {
        "user_id": "analyst-1",
        "roles": ("analyst",),
        "run_id": "run-api-1",
        "trace_id": "trace-api-1",
    }
    assert captured["search"]["enterprise_unavailable_reason"] == "release_unavailable"
    assert captured["search"]["enterprise_store"] is None


def test_enterprise_search_rejects_client_tenant_override(monkeypatch) -> None:
    monkeypatch.setattr(knowledge, "enterprise_mode", lambda: True)
    monkeypatch.setattr(knowledge, "enterprise_retrieval_runtime", lambda: object())
    response = _client("analyst").get(
        "/api/knowledge/search?q=peak&tenant_id=other"
    )
    assert response.status_code == 400

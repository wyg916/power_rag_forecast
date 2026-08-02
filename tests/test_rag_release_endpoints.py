from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import knowledge
from backend.app.main import app


client = TestClient(app)
ADMIN_HEADERS = {"X-User": "release-admin", "X-Role": "admin"}


def test_release_routes_are_registered_with_required_permissions(monkeypatch) -> None:
    monkeypatch.setattr(
        knowledge.release_control,
        "list_releases",
        lambda **_: [{"release_id": "RAG-R1", "status": "candidate"}],
    )
    response = client.get("/api/knowledge/releases", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_release_action_binds_tenant_and_actor_from_authenticated_context(
    monkeypatch,
) -> None:
    captured = {}

    def act(**kwargs):
        captured.update(kwargs)
        return {"release_id": kwargs["release_id"], "status": "validated"}

    monkeypatch.setattr(knowledge.release_control, "act", act)
    response = client.post(
        "/api/knowledge/releases/RAG-R1/validate",
        headers={**ADMIN_HEADERS, "X-Trace-Id": "trace_api_test", "X-Run-Id": "run_api_test"},
    )

    assert response.status_code == 200
    context = captured["context"]
    assert context.tenant_id == "default"
    assert context.actor_id
    assert context.trace_id == "trace_api_test"
    assert context.run_id == "run_api_test"


def test_release_create_rejects_client_tenant_override() -> None:
    response = client.post(
        "/api/knowledge/releases",
        headers=ADMIN_HEADERS,
        json={
            "tenant_id": "other",
            "release_id": "RAG-R2",
            "source_ledger_sha256": "a" * 64,
            "candidate_manifest_sha256": "b" * 64,
            "embedding_profile": {
                "provider": "sentence_transformers",
                "model": "BAAI/bge-large-zh-v1.5",
                "version": "sha256:model",
                "dimension": 1024,
                "sparse_profile": "bm25-zh-v1",
            },
            "idempotency_key": "release-rag-r2",
        },
    )
    assert response.status_code == 422


def test_release_write_routes_are_guarded_by_publish_permission() -> None:
    response = client.post(
        "/api/knowledge/releases/RAG-R1/publish",
        headers={"X-User": "viewer-1", "X-Role": "viewer"},
    )
    assert response.status_code == 403

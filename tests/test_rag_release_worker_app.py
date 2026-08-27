from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.workers import rag_release_worker_app as module


TOKEN = "release-worker-test-token-0001"


class FakeRuntime:
    def action(self, **kwargs):
        return {
            "release_id": kwargs["release_id"],
            "status": "validated",
            "is_current": False,
        }

    def admit(self, **kwargs):
        return {
            "release_id": kwargs["release_id"],
            "status": "candidate",
            "is_current": False,
        }


def _payload() -> dict:
    return {
        "tenant_id": "default",
        "actor_id": "admin-1",
        "run_id": "run-worker-test",
        "trace_id": "trace-worker-test",
        "release_id": "RAG-R1",
        "request": {},
    }


def test_worker_requires_its_separate_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("RAG_RELEASE_WORKER_TOKEN", TOKEN)
    monkeypatch.setattr(module, "get_runtime", lambda: FakeRuntime())
    client = TestClient(module.app)

    assert client.post("/v1/releases/validate", json=_payload()).status_code == 401
    response = client.post(
        "/v1/releases/validate",
        json=_payload(),
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 200
    assert response.json()["release"]["release_id"] == "RAG-R1"


def test_worker_health_does_not_expose_secrets() -> None:
    response = TestClient(module.app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "service": "rag_release_worker"}


def test_worker_rejects_tenant_override(monkeypatch) -> None:
    monkeypatch.setenv("RAG_RELEASE_WORKER_TOKEN", TOKEN)
    monkeypatch.setattr(module, "get_runtime", lambda: FakeRuntime())
    client = TestClient(module.app)
    payload = _payload() | {"tenant_id": "other"}
    response = client.post(
        "/v1/releases/publish",
        json=payload,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 400


def test_admin_secret_is_confined_to_worker_runtime_source() -> None:
    api_source = __import__(
        "inspect"
    ).getsource(__import__("backend.app.services.rag_release_api_service", fromlist=["x"]))
    assert "QDRANT_ADMIN_API_KEY" not in api_source

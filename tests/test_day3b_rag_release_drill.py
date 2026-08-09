from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from scripts.day3b_rag_release_drill import (
    _post_rollback_smoke,
    _reranker_identity_ready,
    _wait_for_post_warm_qdrant,
)
from backend.app.services.rag_release_worker_runtime import (
    QdrantReleaseAdmin,
    _qdrant_loopback_endpoint,
)
from tests.evaluation.run_ai_assistant_eval import _evaluate_direct


def test_reranker_readiness_checks_provider_model_version_and_runtime(monkeypatch) -> None:
    version = "sha256:" + "2" * 64
    monkeypatch.setenv("RAG_RERANK_EXPECTED_VERSION", version)
    valid = SimpleNamespace(
        name="bge",
        model="bge-reranker-v2-m3",
        model_version=version,
        runtime="torch_fp32",
    )
    assert _reranker_identity_ready(valid) is True
    assert _reranker_identity_ready(SimpleNamespace(**{**valid.__dict__, "name": "fallback"})) is False
    assert _reranker_identity_ready(SimpleNamespace(**{**valid.__dict__, "model": "other"})) is False
    assert _reranker_identity_ready(SimpleNamespace(**{**valid.__dict__, "model_version": "bad"})) is False
    assert _reranker_identity_ready(SimpleNamespace(**{**valid.__dict__, "runtime": "onnx"})) is False


class _SnapshotResponse(BytesIO):
    status = 206

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_snapshot_readable_requires_listed_and_downloadable_bytes(monkeypatch) -> None:
    admin = object.__new__(QdrantReleaseAdmin)
    admin.endpoint = "https://127.0.0.1:6333"
    admin.api_key = "redacted-test-key"
    admin.context = object()
    monkeypatch.setattr(admin, "snapshot_exists", lambda *_args: True)
    monkeypatch.setattr(
        "backend.app.services.rag_release_worker_runtime.urlopen",
        lambda *_args, **_kwargs: _SnapshotResponse(b"snapshot-prefix"),
    )
    assert admin.snapshot_readable("rag_chunks_RAG-R1", "snapshot-1") is True


def test_snapshot_readable_fails_closed_when_not_listed(monkeypatch) -> None:
    admin = object.__new__(QdrantReleaseAdmin)
    monkeypatch.setattr(admin, "snapshot_exists", lambda *_args: False)
    assert admin.snapshot_readable("rag_chunks_RAG-R1", "snapshot-1") is False


def test_qdrant_release_admin_uses_the_ipv4_loopback_binding() -> None:
    assert _qdrant_loopback_endpoint("6333") == "https://127.0.0.1:6333"


def test_post_warm_qdrant_waits_until_green(monkeypatch) -> None:
    values = iter(
        [
            {"status": "yellow", "update_queue_length": 0},
            {"status": "green", "update_queue_length": 0},
        ]
    )
    monkeypatch.setattr(
        "scripts.day3b_rag_release_drill._qdrant_readiness_facts",
        lambda _qdrant: next(values),
    )
    facts, history = _wait_for_post_warm_qdrant(
        object(), attempts=2, interval_seconds=0
    )
    assert facts == {"status": "green", "update_queue_length": 0}
    assert [row["status"] for row in history] == ["yellow", "green"]


def test_direct_ai_evaluator_forwards_authoritative_rag_runtime(monkeypatch) -> None:
    captured = {}

    def fake_answer(_question, **kwargs):
        captured.update(kwargs)
        return {
            "answer": "safe",
            "refused": True,
            "domain": "",
            "source_type": "unavailable",
            "citations": [],
            "tool_calls": [],
        }

    monkeypatch.setattr(
        "backend.app.ai_assistant.service.answer_chat_accurate", fake_answer
    )
    identity = object()
    rag_context = object()
    enterprise_store = object()
    result = _evaluate_direct(
        {
            "question_id": "DAY3B-AI-001",
            "question": "security probe",
            "required_run_id_behavior": "none",
            "required_facts": ["safe"],
            "forbidden_claims": [],
            "required_tool": "",
            "expected_route": "refuse",
            "expected_domain": "",
            "expected_source_type": "unavailable",
            "required_citations": False,
            "security_expectation": "refuse",
        },
        "day3b-no-business-run",
        identity=identity,
        rag_context=rag_context,
        enterprise_store=enterprise_store,
    )
    assert result["actual_route"] == "refuse"
    assert captured["identity"] is identity
    assert captured["rag_context"] is rag_context
    assert captured["enterprise_store"] is enterprise_store


def test_post_rollback_smoke_accepts_expected_runtime_rejection(monkeypatch) -> None:
    from fastapi import HTTPException
    from backend.app.services.rag_qdrant_transport import QdrantReadError

    monkeypatch.setattr(
        "backend.app.services.rag_qdrant_transport.enterprise_runtime_for_user",
        lambda _user: (_ for _ in ()).throw(
            QdrantReadError("published_release_fact_mismatch")
        ),
    )
    monkeypatch.setattr(
        "backend.app.api.v1.endpoints.assistant.ai_rag_answer_read_only",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            HTTPException(503, "enterprise_rag_runtime_unavailable")
        ),
    )

    class FakeStore:
        def __init__(self, *_args, **_kwargs):
            pass

        def current_release_id(self, _tenant_id):
            return None

    class FakeQdrant:
        def _request(self, _path):
            return {"result": {"status": "green"}}

        def current_alias(self, _alias):
            return None

    monkeypatch.setattr(
        "scripts.day3b_rag_release_drill.PostgresReleaseStore", FakeStore
    )
    result = _post_rollback_smoke(object(), FakeQdrant(), "probe")
    assert result["status"] == "PASS"
    assert result["runtime_rejection"] == "published_release_fact_mismatch"
    assert result["api_status"] == 503

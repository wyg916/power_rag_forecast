from __future__ import annotations

import hashlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.ai_assistant import service as assistant_service
from backend.app.api.v1.endpoints import assistant
from backend.app.core.security import CurrentUser, ROLE_PERMISSIONS, get_current_user
from backend.app.services.rag_enterprise_runtime import EnterpriseRetrievalBinding
from backend.app.services.rag_grounding_service import validate_candidate_citations
from backend.app.services.rag_runtime_contract import RetrievalContext


class _Store:
    pass


class _Runtime:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.calls: list[dict] = []
        self.store = _Store()

    def bind(self, **kwargs):
        self.calls.append(kwargs)
        if not self.available:
            return EnterpriseRetrievalBinding(
                context=None,
                store=None,
                public_reason="release_unavailable",
                diagnostic_reason="current_published_release_missing",
            )
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
            store=self.store,
        )


def _client(monkeypatch, runtime: _Runtime) -> TestClient:
    app = FastAPI()
    app.include_router(assistant.router)
    user = CurrentUser(
        user_id="analyst-1",
        username="analyst-1",
        role="analyst",
        permissions=sorted(ROLE_PERMISSIONS["analyst"]),
        auth_mode="test",
    )
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(assistant, "enterprise_mode", lambda: True)
    monkeypatch.setattr(assistant, "assistant_retrieval_runtime", lambda: runtime)
    return TestClient(app)


def _citations(quote: str = "尖峰风险") -> list[dict]:
    content = quote + "，需要结合受控事实源复核。"
    item = {
        "document_id": "doc-1",
        "chunk_id": "chunk-1",
        "version_id": "version-1",
        "title": "尖峰风险说明",
        "content": content,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "citation": {
            "version_id": "version-1",
            "page": 3,
            "section_path": ["运行风险"],
            "char_start": 0,
            "char_end": len(quote),
            "bbox": [1.0, 2.0, 10.0, 20.0],
            "asset_id": None,
            "quote": quote,
            "content_hash": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        },
        "final_score": 0.9,
    }
    return validate_candidate_citations([item]).citations


def test_rag_answer_uses_auth_binding_and_returns_unified_grounded_contract(
    monkeypatch,
):
    runtime = _Runtime()
    captured: dict = {}

    def search(question, **kwargs):
        captured.update(question=question, **kwargs)
        return {
            "available": True,
            "release_id": "RAG-R1",
            "citations": _citations(),
            "retrieval": {"available": True},
        }

    monkeypatch.setattr(assistant, "rag_search", search)
    response = _client(monkeypatch, runtime).post(
        "/api/ai/rag-answer",
        headers={"X-Run-ID": "run-ai-1", "X-Trace-ID": "trace-ai-1"},
        json={"question": "如何判断尖峰风险？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert {
        "answer",
        "claims",
        "citations",
        "grounding_status",
        "refusal_reason",
        "release_id",
        "trace_id",
        "degraded_components",
    } <= set(payload)
    assert payload["grounding_status"] == "grounded"
    assert payload["release_id"] == "RAG-R1"
    assert payload["trace_id"] == "trace-ai-1"
    citation_ids = {item["citation_id"] for item in payload["citations"]}
    assert all(set(claim["citation_ids"]) <= citation_ids for claim in payload["claims"])
    assert runtime.calls == [
        {
            "user_id": "analyst-1",
            "roles": ("analyst",),
            "run_id": "run-ai-1",
            "trace_id": "trace-ai-1",
        }
    ]
    assert captured["context"].tenant_id == "default"
    assert captured["enterprise_store"] is runtime.store
    serialized = str(payload).lower()
    for forbidden in (
        "collection",
        "provider",
        "model_path",
        "api_key",
        "current_published_release_missing",
    ):
        assert forbidden not in serialized


def test_rag_answer_fails_closed_without_current_published_release(monkeypatch):
    runtime = _Runtime(available=False)

    def search(question, **kwargs):
        assert kwargs["enterprise_store"] is None
        return {
            "available": False,
            "release_id": "RAG-R1",
            "citations": [],
            "retrieval": {"reason": kwargs["enterprise_unavailable_reason"]},
        }

    monkeypatch.setattr(assistant, "rag_search", search)
    payload = _client(monkeypatch, runtime).post(
        "/api/ai/rag-answer",
        headers={"X-Trace-ID": "trace-ai-2"},
        json={"question": "当前制度如何规定？"},
    ).json()

    assert payload["grounding_status"] == "unavailable"
    assert payload["refusal_reason"] == "release_unavailable"
    assert payload["release_id"] is None
    assert payload["claims"] == payload["citations"] == []
    assert payload["degraded_components"] == ["retrieval"]
    assert "current_published_release_missing" not in str(payload)


def test_assistant_rejects_all_client_tenant_overrides(monkeypatch):
    client = _client(monkeypatch, _Runtime())

    assert client.post(
        "/api/ai/rag-answer", json={"question": "问题", "tenant_id": "other"}
    ).status_code == 400
    assert client.post(
        "/api/ai/rag-answer?tenant_id=other", json={"question": "问题"}
    ).status_code == 400
    assert client.post(
        "/api/ai/rag-answer",
        headers={"X-Tenant-ID": "other"},
        json={"question": "问题"},
    ).status_code == 400
    assert client.post(
        "/api/ai/chat", json={"question": "问题", "tenant_id": "other"}
    ).status_code == 422


def test_main_chat_receives_auth_derived_enterprise_context(monkeypatch):
    runtime = _Runtime()
    captured: dict = {}

    def answer_chat(question, **kwargs):
        captured.update(question=question, **kwargs)
        return {"answer": "ok"}

    monkeypatch.setattr(assistant, "answer_chat", answer_chat)
    response = _client(monkeypatch, runtime).post(
        "/api/ai/chat",
        headers={"X-Run-ID": "run-ai-chat", "X-Trace-ID": "trace-ai-chat"},
        json={"question": "知识库中的制度是什么？"},
    )

    assert response.status_code == 200
    assert captured["retrieval_context"].tenant_id == "default"
    assert captured["retrieval_context"].user_id == "analyst-1"
    assert captured["retrieval_context"].roles == ("analyst",)
    assert captured["enterprise_store"] is runtime.store
    assert captured["trace_id"] == "trace-ai-chat"


def test_main_ai_knowledge_answer_is_rebuilt_from_verified_claims(monkeypatch):
    context = RetrievalContext(
        tenant_id="default",
        user_id="analyst-1",
        roles=("analyst",),
        acl_fingerprint="acl-v1",
        release_id="RAG-R1",
        run_id="run-ai-knowledge",
        trace_id="trace-ai-knowledge",
    )
    monkeypatch.setenv("AI_ASSISTANT_LLM_ENABLED", "0")
    monkeypatch.setattr(assistant_service, "rag_enabled", lambda: True)
    monkeypatch.setattr(
        assistant_service,
        "rag_search",
        lambda *_args, **_kwargs: {
            "available": True,
            "source_type": "published_knowledge",
            "release_id": "RAG-R1",
            "items": [{"title": "尖峰风险说明"}],
            "citations": _citations(),
            "retrieval": {"available": True},
        },
    )

    payload = assistant_service.answer_chat_accurate(
        "PJM 的 LMP 是什么意思？",
        persist=False,
        retrieval_context=context,
        enterprise_store=_Store(),
        trace_id=context.trace_id,
    )

    assert payload["grounding_status"] == "grounded"
    assert payload["release_id"] == "RAG-R1"
    assert payload["run_id"] == "run-ai-knowledge"
    assert payload["trace_id"] == "trace-ai-knowledge"
    assert payload["claims"] and payload["citations"]
    citation_ids = {item["citation_id"] for item in payload["citations"]}
    assert all(set(claim["citation_ids"]) <= citation_ids for claim in payload["claims"])
    assert payload["evidence"] == payload["citations"]


def test_numeric_business_question_does_not_use_rag_as_fact_source(monkeypatch):
    calls = {"rag": 0}

    def supplemental_rag(*_args, **_kwargs):
        calls["rag"] += 1
        return {
            "available": True,
            "release_id": "RAG-R1",
            "items": [{"title": "非事实源"}],
            "citations": _citations("最高电价为 9999"),
            "retrieval": {"available": True},
        }

    monkeypatch.setattr(assistant_service, "rag_enabled", lambda: True)
    monkeypatch.setattr(assistant_service, "rag_search", supplemental_rag)
    payload = assistant_service.answer_chat_accurate(
        "明天电价最高是多少？",
        persist=False,
        trace_id="trace-ai-numeric",
        debug=True,
    )

    assert payload["intent"] == "forecast_max_price"
    assert payload["tool_calls"][0]["tool_name"] == "get_forecast_metrics"
    assert calls["rag"] == 1
    assert "9999" not in payload["answer"]
    assert payload["claims"] == payload["citations"] == []
    assert payload["release_id"] is None

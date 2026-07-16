from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import knowledge as knowledge_endpoint
from backend.app.main import app


client = TestClient(app)


def test_knowledge_documents_endpoint_contract(monkeypatch):
    monkeypatch.setattr(
        knowledge_endpoint,
        "list_knowledge_documents",
        lambda page=1, page_size=20, search="": {
            "available": True,
            "items": [{"doc_id": "kb_test", "title": "浙江省电力市场交易规则", "chunk_count": 2, "status": "indexed"}],
            "total": 1,
            "page": page,
            "page_size": page_size,
        },
    )

    response = client.get("/api/knowledge/documents", headers={"X-User": "viewer1", "X-Role": "viewer"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["doc_id"] == "kb_test"


def test_knowledge_qa_test_uses_rag_and_returns_answer(monkeypatch):
    monkeypatch.setattr(knowledge_endpoint, "ensure_seed_knowledge", lambda: {"available": True})
    monkeypatch.setattr(
        knowledge_endpoint,
        "rag_search",
        lambda query, top_k=5: {
            "query": query,
            "items": [{"chunk_id": "c1", "title": "规则", "content": "分时电价规则", "final_score": 0.9}],
            "retrieval": {"mode": "hybrid"},
            "timings_ms": {"total_ms": 1.0},
        },
    )
    monkeypatch.setattr(knowledge_endpoint, "record_search_result", lambda query, top_k, result: {"available": True, "search_id": "ks_test"})
    monkeypatch.setattr(
        knowledge_endpoint,
        "run_qa_from_search",
        lambda question, top_k, search_result, started_at: {
            **search_result,
            "answer": "结论：可参考分时电价规则。",
            "answer_blocks": [{"key": "conclusion", "title": "结论", "tone": "success", "content": "可参考分时电价规则。"}],
            "passed": True,
            "qa_test": {"available": True, "test_id": "kqa_test"},
        },
    )

    response = client.post(
        "/api/knowledge/qa-test",
        headers={"X-User": "viewer1", "X-Role": "viewer"},
        json={"question": "分时电价规则是什么？", "top_k": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    assert payload["answer_blocks"][0]["title"] == "结论"
    assert payload["qa_test"]["test_id"] == "kqa_test"


def test_knowledge_upload_requires_write_permission(monkeypatch):
    monkeypatch.setattr(knowledge_endpoint, "upsert_document", lambda **kwargs: {"available": True, "doc_id": "kb_uploaded", "chunks": 1})
    monkeypatch.setattr(knowledge_endpoint, "write_audit_log", lambda **kwargs: True)

    denied = client.post(
        "/api/knowledge/upload",
        headers={"X-User": "viewer1", "X-Role": "viewer"},
        files={"file": ("policy.md", b"# test", "text/markdown")},
    )
    allowed = client.post(
        "/api/knowledge/upload",
        headers={"X-User": "analyst1", "X-Role": "analyst"},
        files={"file": ("policy.md", b"# test", "text/markdown")},
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["doc_id"] == "kb_uploaded"

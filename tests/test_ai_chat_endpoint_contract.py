from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import assistant as assistant_endpoint
from backend.app.ai.chat_memory import MemoryNotFoundError, MemoryPersistenceError
from backend.app.ai_assistant.service import ModelProviderUnavailableError
from backend.app.ai_assistant import attachments as attachment_store
from backend.app.core.security import CurrentUser, get_current_user
from backend.app.main import app


client = TestClient(app)


def test_ai_chat_reuses_answer_chat(monkeypatch):
    captured: dict[str, object] = {}

    def fake_answer_chat(question, **kwargs):
        captured["question"] = question
        captured["kwargs"] = kwargs
        return {
            "session_id": "chat_test_session",
            "answer": "结论：已完成问答链路测试。\n\n数据依据：测试桩返回。",
            "evidence_summary": ["test_source"],
            "knowledge_evidence_summary": [],
            "warnings": [],
        }

    monkeypatch.setattr(assistant_endpoint, "answer_chat", fake_answer_chat)

    response = client.post("/api/ai/chat", json={"question": "测试问答链路"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "chat_test_session"
    assert payload["answer"].startswith("结论：")
    assert captured["question"] == "测试问答链路"
    identity = captured["kwargs"]["identity"]
    assert identity.user_id == "pytest-admin"
    assert identity.tenant_id == "default"


def test_ai_chat_returns_503_when_explicit_provider_is_unavailable(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise ModelProviderUnavailableError("mimo", "provider unavailable")

    monkeypatch.setattr(assistant_endpoint, "answer_chat", unavailable)

    response = client.post(
        "/api/ai/chat",
        json={"question": "你好", "model_provider": "mimo"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "PROVIDER_UNAVAILABLE",
        "provider": "mimo",
        "retryable": True,
    }


def test_enterprise_ai_chat_injects_authenticated_rag_runtime(monkeypatch):
    captured: dict[str, object] = {}
    context, store = object(), object()

    monkeypatch.setattr(assistant_endpoint, "enterprise_mode", lambda: True)
    monkeypatch.setattr(
        assistant_endpoint,
        "enterprise_runtime_for_user",
        lambda user: (context, store),
    )

    def fake_answer_chat(question, **kwargs):
        captured.update(question=question, **kwargs)
        return {"session_id": "chat_enterprise", "answer": "已接入企业知识库。"}

    monkeypatch.setattr(assistant_endpoint, "answer_chat", fake_answer_chat)
    response = client.post(
        "/api/ai/chat",
        headers={"X-User": "analyst1", "X-Role": "analyst"},
        json={"question": "电力市场规则是什么？"},
    )

    assert response.status_code == 200
    assert captured["rag_context"] is context
    assert captured["enterprise_store"] is store


def test_ai_rag_answer_rejects_tenant_override():
    response = client.post(
        "/api/ai/rag-answer",
        headers={"X-User": "analyst1", "X-Role": "analyst"},
        json={"question": "电力市场规则是什么？", "tenant_id": "other"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "tenant_override_forbidden"


def test_ai_chat_rejects_identity_body_override():
    response = client.post(
        "/api/ai/chat",
        json={"question": "identity tamper", "user_id": "victim", "tenant_id": "tenant_b"},
    )
    assert response.status_code == 422


def test_ai_chat_stream_reuses_answer_chat(monkeypatch):
    captured: dict[str, object] = {}

    def fake_answer_chat(question, **kwargs):
        captured["question"] = question
        captured["kwargs"] = kwargs
        return {
            "session_id": "chat_stream_session",
            "answer": "结论：流式输出复用主问答链路。",
            "evidence_summary": ["stream_source"],
            "knowledge_evidence_summary": ["stream_doc"],
            "tool_calls": [{"name": "query_forecast", "status": "done"}],
            "warnings": [],
        }

    monkeypatch.setattr(assistant_endpoint, "answer_chat", fake_answer_chat)

    response = client.post("/api/ai/chat/stream", json={"question": "测试流式问答"})

    assert response.status_code == 200
    body = response.text
    assert "event: meta" in body
    assert "event: status" in body
    assert "event: tool_status" in body
    assert "event: delta" in body
    assert "event: done" in body
    assert "流式输出复用主问答链路" in body
    assert captured["question"] == "测试流式问答"


def test_ai_export_conversation_docx():
    response = client.post(
        "/api/ai/chat/sessions/export?format=docx",
        json={
            "session_id": "export_session",
            "messages": [
                {"role": "user", "content": "请分析明日电价", "created_at": "10:00"},
                {"role": "assistant", "content": "结论：已生成分析。", "created_at": "10:01"},
            ],
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert response.content.startswith(b"PK")


def test_ai_export_pdf_reports_unavailable():
    response = client.post(
        "/api/ai/chat/sessions/export?format=pdf",
        json={"session_id": "export_session", "messages": []},
    )

    assert response.status_code == 501
    assert "PDF" in response.json()["detail"]


def test_ai_upload_attachment_saves_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(attachment_store, "ROOT", tmp_path)
    audits: list[dict[str, object]] = []
    monkeypatch.setattr(assistant_endpoint, "write_audit_log", lambda **kwargs: audits.append(kwargs) or True)

    response = client.post(
        "/api/ai/attachments",
        files={"file": ("question.txt", b"hello assistant", "text/plain")},
        data={"session_id": "sess_upload"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["file_name"] == "question.txt"
    assert payload["status"] == "ready"
    detail = client.get(
        f"/api/ai/attachments/{payload['attachment_id']}?session_id=sess_upload"
    )
    assert detail.status_code == 200
    assert "chunks" not in detail.json() and "properties" not in detail.json()
    deleted = client.delete(f"/api/ai/attachments/{payload['attachment_id']}")
    deleted_again = client.delete(f"/api/ai/attachments/{payload['attachment_id']}")
    assert deleted.status_code == 200 and deleted.json()["status"] == "deleted"
    assert deleted_again.status_code == 200 and deleted_again.json()["status"] == "deleted"
    assert [item["action"] for item in audits] == [
        "ai.attachment.upload", "ai.attachment.delete", "ai.attachment.delete"
    ]
    assert all("content" not in item["metadata"] for item in audits)


def test_attachment_endpoint_enforces_jwt_user_and_tenant_scope(monkeypatch, tmp_path):
    monkeypatch.setattr(attachment_store, "ROOT", tmp_path)
    monkeypatch.setattr(assistant_endpoint, "write_audit_log", lambda **_kwargs: True)

    def jwt_user(user_id: str, tenant_id: str) -> CurrentUser:
        return CurrentUser(
            user_id=user_id,
            username=user_id,
            role="analyst",
            permissions=["assistant:use"],
            auth_mode="jwt",
            tenant_id=tenant_id,
            workspace_id="workspace-a",
            role_ids=("analyst",),
        )

    original = app.dependency_overrides.get(get_current_user)
    try:
        app.dependency_overrides[get_current_user] = lambda: jwt_user("user-a", "tenant-a")
        uploaded = client.post(
            "/api/ai/attachments",
            files={"file": ("owned.txt", b"private evidence", "text/plain")},
            data={"session_id": "sess-owned"},
        )
        assert uploaded.status_code == 200
        attachment_id = uploaded.json()["attachment_id"]

        app.dependency_overrides[get_current_user] = lambda: jwt_user("user-b", "tenant-a")
        assert client.get(f"/api/ai/attachments/{attachment_id}").status_code == 404
        assert client.delete(f"/api/ai/attachments/{attachment_id}").status_code == 404

        app.dependency_overrides[get_current_user] = lambda: jwt_user("user-a", "tenant-b")
        assert client.get(f"/api/ai/attachments/{attachment_id}").status_code == 404

        app.dependency_overrides[get_current_user] = lambda: jwt_user("user-a", "tenant-a")
        wrong_session = client.get(f"/api/ai/attachments/{attachment_id}?session_id=sess-other")
        assert wrong_session.status_code == 403
        assert client.get("/api/ai/attachments/att_00000000000000000000000000000000").status_code == 404
    finally:
        if original is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = original


def test_file_chat_binds_attachment_ids_returns_citation_and_rejects_deleted_reuse(monkeypatch, tmp_path):
    monkeypatch.setattr(attachment_store, "ROOT", tmp_path)
    monkeypatch.setattr(assistant_endpoint, "write_audit_log", lambda **_kwargs: True)
    captured: dict[str, object] = {}

    def grounded_file_answer(question, **kwargs):
        captured["question"] = question
        captured["attachment_ids"] = kwargs["attachment_ids"]
        captured["attachment_evidence"] = kwargs["attachment_evidence"]
        captured["knowledge_scope"] = kwargs["knowledge_scope"]
        return {
            "session_id": "sess_file",
            "answer": "附件说明了受控结论。",
            "citations": [],
            "evidence_summary": [],
            "warnings": [],
            "attachment_grounding": {
                "context_applied": True,
                "knowledge_scope": kwargs["knowledge_scope"],
                "selected_attachment_ids": kwargs["attachment_ids"],
                "source_ids": [item["source_id"] for item in kwargs["attachment_evidence"]],
                "chunk_count": len(kwargs["attachment_evidence"]),
            },
        }

    monkeypatch.setattr(assistant_endpoint, "answer_chat", grounded_file_answer)
    uploaded = client.post(
        "/api/ai/attachments",
        files={"file": ("evidence.txt", b"controlled attachment evidence", "text/plain")},
        data={"session_id": "sess_file"},
    )
    assert uploaded.status_code == 200
    attachment_id = uploaded.json()["attachment_id"]

    answered = client.post("/api/ai/chat", json={
        "question": "附件说了什么？",
        "session_id": "sess_file",
        "mode": "file",
        "attachment_ids": [attachment_id],
        "knowledge_scope": "attachments",
    })
    assert answered.status_code == 200
    payload = answered.json()
    assert payload["attachment_ids"] == [attachment_id]
    assert payload["attachment_citations"][0]["attachment_id"] == attachment_id
    assert payload["attachment_citations"][0]["file_name"] == "evidence.txt"
    assert payload["attachment_citations"][0]["source_id"].startswith(f"attachment:{attachment_id}:")
    assert payload["attachment_claims"][0]["citation_ids"] == [
        payload["attachment_citations"][0]["citation_id"]
    ]
    assert payload["grounding_status"] == "grounded"
    assert captured["question"] == "附件说了什么？"
    assert captured["attachment_evidence"][0]["text"] == "controlled attachment evidence"
    assert captured["attachment_ids"] == [attachment_id]
    assert captured["knowledge_scope"] == "attachments"

    assert client.delete(f"/api/ai/attachments/{attachment_id}").status_code == 200
    reused = client.post("/api/ai/chat", json={
        "question": "再次使用附件。",
        "session_id": "sess_file",
        "mode": "file",
        "attachment_ids": [attachment_id],
    })
    assert reused.status_code == 410
    assert reused.json()["detail"]["code"] == "ATTACHMENT_NOT_AVAILABLE"


def test_session_crud_uses_authoritative_identity_and_hides_foreign_rows(monkeypatch):
    captured: list[tuple[str, str]] = []

    def fake_list(identity, page=1, page_size=50):
        captured.append(("list", identity.user_id))
        return {"items": [{"session_id": "owned"}], "total": 1, "page": page, "page_size": page_size}

    def foreign(_identity):
        raise MemoryNotFoundError("foreign")

    monkeypatch.setattr(assistant_endpoint, "list_chat_sessions", fake_list)
    monkeypatch.setattr(assistant_endpoint, "get_chat_session", foreign)

    listed = client.get("/api/ai/chat/sessions?page=1&page_size=1")
    assert listed.status_code == 200
    assert listed.json()["sessions"] == [{"session_id": "owned"}]
    assert captured == [("list", "pytest-admin")]

    detail = client.get("/api/ai/chat/sessions/foreign-session")
    assert detail.status_code == 404
    assert detail.json()["detail"] == "assistant_memory_not_found"


def test_memory_failure_is_not_reported_as_success(monkeypatch):
    monkeypatch.setattr(
        assistant_endpoint,
        "list_chat_sessions",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(MemoryPersistenceError("db down")),
    )
    response = client.get("/api/ai/chat/sessions")
    assert response.status_code == 503
    assert response.json()["detail"] == "assistant_memory_unavailable"

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import assistant as assistant_endpoint
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
    assert "event: intent" in body
    assert "event: tool_start" in body
    assert "event: rag_result" in body
    assert "event: token" in body
    assert "event: final" in body
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
    monkeypatch.setattr(assistant_endpoint, "ASSISTANT_UPLOAD_DIR", tmp_path)

    response = client.post(
        "/api/ai/attachments",
        files={"file": ("question.txt", b"hello assistant", "text/plain")},
        data={"kind": "attachment"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "question.txt"
    assert payload["summary"] == "hello assistant"
    assert (tmp_path / "metadata.jsonl").exists()

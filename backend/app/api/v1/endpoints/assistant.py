from __future__ import annotations

import io
import json
import re
import time
import uuid
from pathlib import Path
from typing import Annotated, Any, Iterator

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response, StreamingResponse

from ....core.redaction import mask_secret_fields
from ....core.security import CurrentUser, require_permission
from ....repositories.audit_repository import write_audit_log
from ....repositories.knowledge_repository import build_qa_answer
from ....services.rag_service import rag_search
from ....services.rag_qdrant_transport import enterprise_runtime_for_user
from ....services.rag_runtime_contract import enterprise_mode
from ....services.rag_grounding_service import validate_claim_bindings
from ....ai.chat_memory import (
    MemoryConflictError,
    MemoryNotFoundError,
    MemoryPersistenceError,
    assert_session_available,
    delete_chat_session,
    get_chat_session,
    list_chat_sessions,
    save_answer_feedback,
    save_chat_feedback,
    update_chat_session,
)
from ....ai.identity_context import IdentityContext
from ....ai.assistant_service import answer_chat
from ....platform_services import generate_ai_insights
from ....schemas import AgentAnalyzeRequest, AnswerFeedbackRequest, ChatFeedbackRequest, ChatRequest
from backend.app.ai_assistant.service import ModelProviderUnavailableError, answer_chat_accurate


router = APIRouter()

ASSISTANT_UPLOAD_DIR = Path(__file__).resolve().parents[4] / "data" / "assistant_uploads"
ASSISTANT_UPLOAD_LIMIT_BYTES = 20 * 1024 * 1024


def _identity(user: CurrentUser, session_id: str = "", run_id: str = "latest") -> IdentityContext:
    return IdentityContext.from_user(user, session_id=session_id, run_id=run_id)


def _raise_memory_http(exc: Exception) -> None:
    if isinstance(exc, (MemoryNotFoundError, MemoryConflictError)):
        raise HTTPException(status_code=404, detail="assistant_memory_not_found") from exc
    raise HTTPException(status_code=503, detail="assistant_memory_unavailable") from exc


def _raise_model_provider_http(exc: ModelProviderUnavailableError) -> None:
    raise HTTPException(
        status_code=503,
        detail={"code": "model_provider_unavailable", "provider": exc.provider},
    ) from exc


def _stream_event(event: str, data: dict[str, Any]) -> str:
    safe_data = mask_secret_fields(data)
    return f"event: {event}\ndata: {json.dumps(jsonable_encoder(safe_data), ensure_ascii=False)}\n\n"


def _chunk_text(text: str, chunk_size: int = 36) -> Iterator[str]:
    value = text or ""
    for start in range(0, len(value), chunk_size):
        yield value[start : start + chunk_size]


def _safe_filename(filename: str | None) -> str:
    raw = (filename or "assistant_attachment").strip()
    name = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", raw, flags=re.UNICODE).strip("._")
    return name or "assistant_attachment"


def _append_upload_metadata(metadata: dict[str, Any]) -> None:
    ASSISTANT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    metadata_path = ASSISTANT_UPLOAD_DIR / "metadata.jsonl"
    with metadata_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(jsonable_encoder(metadata), ensure_ascii=False) + "\n")


def _format_messages_for_export(messages: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for item in messages:
        role = "用户" if item.get("role") == "user" else "AI 助手"
        created_at = str(item.get("created_at") or item.get("createdAt") or "")
        content = str(mask_secret_fields(str(item.get("content") or ""))).strip()
        if content:
            rows.append((role, created_at, content))
    return rows


def _build_conversation_docx(payload: dict[str, Any]) -> bytes:
    from docx import Document

    document = Document()
    document.add_heading("AI 助手会话导出", level=1)
    session_id = mask_secret_fields(str(payload.get("session_id") or "local_session"))
    document.add_paragraph(f"会话 ID：{session_id}")
    document.add_paragraph(f"导出时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    document.add_paragraph("说明：本文件由后端导出接口生成，内容来自当前会话消息，不包含隐藏调试 Trace。")

    for role, created_at, content in _format_messages_for_export(payload.get("messages") or []):
        document.add_heading(f"{role}{f' · {created_at}' if created_at else ''}", level=2)
        for paragraph in content.splitlines() or [content]:
            if paragraph.strip():
                document.add_paragraph(paragraph.strip())

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _enterprise_runtime(user: CurrentUser) -> dict[str, Any]:
    if not enterprise_mode():
        return {}
    try:
        context, store = enterprise_runtime_for_user(user)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="enterprise_rag_runtime_unavailable"
        ) from exc
    return {"rag_context": context, "enterprise_store": store}


def _answer_contract(
    payload: dict[str, Any], *, release_id: str | None = None,
    retrieval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = dict(payload)
    citations = list(response.get("citations") or [])
    claims = list(response.get("claims") or [])
    if citations and not claims and all(item.get("citation_id") for item in citations):
        claims = [{
            "claim_id": "claim-" + uuid.uuid4().hex[:24],
            "text": str(response.get("answer") or "").strip(),
            "citation_ids": [str(item["citation_id"]) for item in citations],
        }]
    grounding = validate_claim_bindings(claims, citations)
    refused = bool(response.get("refused") or not response.get("available", True))
    response.update(
        claims=grounding.claims if grounding.available else [],
        grounding_status=(
            grounding.grounding_status
            if grounding.available
            else "unavailable" if refused or enterprise_mode() else "not_required"
        ),
        refusal_reason=(
            str(
                response.get("refusal_reason")
                or response.get("security_reason")
                or response.get("unavailable_reason")
                or grounding.refusal_reason
            )
            if refused or (citations and not grounding.available)
            else ""
        ),
        release_id=response.get("release_id") or release_id,
        trace_id=response.get("trace_id") or "trace_" + uuid.uuid4().hex[:24],
        degraded_components=list(
            response.get("degraded_components")
            or (retrieval or {}).get("degraded_components")
            or []
        ),
    )
    return response


def _answer_chat_from_payload(
    payload: ChatRequest, debug_allowed: bool, user: CurrentUser
) -> dict:
    try:
        return _answer_contract(answer_chat(
            payload.question,
            session_id=payload.session_id,
            run_id=payload.run_id,
            market=payload.market,
            date=payload.date,
            page_context=payload.page_context,
            scenario=payload.scenario,
            user_role=payload.user_role,
            answer_style=payload.answer_style,
            model_provider=payload.model_provider,
            debug=debug_allowed,
            identity=_identity(user, payload.session_id or "", payload.run_id),
            **_enterprise_runtime(user),
        ))
    except ModelProviderUnavailableError as exc:
        _raise_model_provider_http(exc)
        raise AssertionError("unreachable")
    except (MemoryPersistenceError, MemoryNotFoundError, MemoryConflictError) as exc:
        _raise_memory_http(exc)
        raise AssertionError("unreachable")


@router.post("/api/ai/rag-answer")
def ai_rag_answer_read_only(
    user: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict:
    question = str(payload.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")
    if "tenant_id" in payload or "tenantId" in payload:
        raise HTTPException(status_code=400, detail="tenant_override_forbidden")
    top_k = max(1, min(int(payload.get("top_k") or 5), 20))
    source_types = payload.get("source_types") or []
    if isinstance(source_types, str):
        source_types = [item.strip() for item in source_types.split(",") if item.strip()]
    result = rag_search(
        question,
        top_k=top_k,
        domain=str(payload.get("domain") or "").strip(),
        source_types=[str(item).strip() for item in source_types if str(item).strip()],
        include_historical=bool(payload.get("include_historical", False)),
        include_demo=bool(payload.get("include_demo", False)),
        tenant_id=user.tenant_id,
        **(
            {
                "context": runtime["rag_context"],
                "enterprise_store": runtime["enterprise_store"],
            }
            if (runtime := _enterprise_runtime(user))
            else {}
        ),
    )
    return _answer_contract(
        {
            **build_qa_answer(question, result),
            "citations": result.get("citations") or [],
            "evidence": result.get("citations") or [],
            "retrieval": result.get("retrieval") or {},
            "read_only": True,
        },
        release_id=result.get("release_id"),
        retrieval=result.get("retrieval") or {},
    )


@router.post("/api/ai/chat")
def ai_chat(
    payload: ChatRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
) -> dict:
    debug_allowed = bool(payload.debug and user.can_debug())
    if payload.debug:
        write_audit_log(
            action="ai.debug_view",
            user=user,
            resource_type="ai_chat",
            status="success" if debug_allowed else "denied",
            ip_address=request.client.host if request.client else "",
            metadata={"requested_debug": True, "allowed": debug_allowed, "question_length": len(payload.question or "")},
        )
    return _answer_chat_from_payload(payload, debug_allowed, user)


@router.post("/api/ai/chat/stream")
def ai_chat_stream(
    payload: ChatRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
) -> StreamingResponse:
    debug_allowed = bool(payload.debug and user.can_debug())
    if payload.debug:
        write_audit_log(
            action="ai.debug_view",
            user=user,
            resource_type="ai_chat_stream",
            status="success" if debug_allowed else "denied",
            ip_address=request.client.host if request.client else "",
            metadata={"requested_debug": True, "allowed": debug_allowed, "question_length": len(payload.question or "")},
        )
    if payload.session_id:
        try:
            assert_session_available(_identity(user, payload.session_id, payload.run_id))
        except (MemoryPersistenceError, MemoryNotFoundError, MemoryConflictError) as exc:
            _raise_memory_http(exc)

    def generate() -> Iterator[str]:
        yield _stream_event("intent", {"message": "已接收问题，正在识别业务意图。"})
        yield _stream_event("tool_start", {"name": "AI/RAG/业务工具链", "message": "正在复用主问答链路生成结果。"})
        try:
            response = _answer_chat_from_payload(payload, debug_allowed, user)
            for item in response.get("evidence_summary") or []:
                yield _stream_event("rag_result", {"source": item})
            for item in response.get("knowledge_evidence_summary") or []:
                yield _stream_event("rag_result", {"source": item, "type": "knowledge"})
            for call in response.get("tool_calls") or []:
                yield _stream_event(
                    "tool_result",
                    {
                        "name": call.get("name") or call.get("tool_name") or "tool",
                        "status": call.get("status") or "done",
                    },
                )
            for chunk in _chunk_text(str(response.get("answer") or "")):
                yield _stream_event("token", {"text": chunk})
                time.sleep(0.01)
            yield _stream_event("final", response)
        except Exception as exc:  # pragma: no cover - streamed to browser
            yield _stream_event("error", {"message": str(exc)})

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/api/ai/attachments")
async def ai_upload_attachment(
    _: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
    file: UploadFile = File(...),
    kind: str = Form("attachment"),
) -> dict:
    content = await file.read()
    if len(content) > ASSISTANT_UPLOAD_LIMIT_BYTES:
        raise HTTPException(status_code=413, detail="附件超过 20MB，暂不支持上传。")

    attachment_id = f"att_{uuid.uuid4().hex}"
    safe_name = _safe_filename(file.filename)
    stored_name = f"{attachment_id}_{safe_name}"
    ASSISTANT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_path = ASSISTANT_UPLOAD_DIR / stored_name
    stored_path.write_bytes(content)

    preview = ""
    if (file.content_type or "").startswith("text/") or safe_name.lower().endswith((".txt", ".csv", ".md", ".json")):
        preview = content[:2048].decode("utf-8", errors="ignore").strip()

    metadata = {
        "attachment_id": attachment_id,
        "filename": safe_name,
        "kind": kind,
        "content_type": file.content_type or "application/octet-stream",
        "size": len(content),
        "stored_path": str(stored_path),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "preview": preview[:500],
    }
    _append_upload_metadata(metadata)
    return {
        "attachment_id": attachment_id,
        "filename": safe_name,
        "kind": kind,
        "content_type": metadata["content_type"],
        "size": len(content),
        "summary": preview[:120] if preview else "附件已由后端保存，可随本次问题作为上下文引用。",
    }


@router.post("/api/ai/chat/sessions/export")
def ai_export_conversation(
    _: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
    payload: dict[str, Any] = Body(...),
    format: str = "docx",
) -> Response:
    normalized_format = format.lower().strip()
    if normalized_format == "pdf":
        raise HTTPException(status_code=501, detail="PDF 导出引擎尚未部署，请先使用 Word 导出。")
    if normalized_format != "docx":
        raise HTTPException(status_code=400, detail="仅支持 docx 或 pdf 导出格式。")

    content = _build_conversation_docx(payload)
    filename = f"assistant_conversation_{int(time.time())}.docx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/api/ai/agent/analyze")
def ai_agent_analyze(
    payload: AgentAnalyzeRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
) -> dict:
    debug_allowed = bool(payload.debug and user.can_debug())
    if payload.debug:
        write_audit_log(
            action="ai.debug_view",
            user=user,
            resource_type="ai_agent",
            status="success" if debug_allowed else "denied",
            ip_address=request.client.host if request.client else "",
            metadata={"requested_debug": True, "allowed": debug_allowed, "question_length": len(payload.question or "")},
        )
    try:
        return _answer_contract(answer_chat_accurate(
            payload.question,
            session_id=payload.session_id,
            run_id=payload.run_id,
            market=payload.market,
            date=payload.date,
            page_context=payload.page_context,
            scenario=payload.scenario,
            user_role=payload.user_role,
            answer_style=payload.answer_style,
            model_provider=payload.model_provider,
            debug=debug_allowed,
            persist=True,
            identity=_identity(user, payload.session_id or "", payload.run_id),
            **_enterprise_runtime(user),
        ))
    except ModelProviderUnavailableError as exc:
        _raise_model_provider_http(exc)
        raise AssertionError("unreachable")
    except (MemoryPersistenceError, MemoryNotFoundError, MemoryConflictError) as exc:
        _raise_memory_http(exc)
        raise AssertionError("unreachable")


@router.post("/api/ai/chat/feedback")
def ai_chat_feedback(
    payload: ChatFeedbackRequest,
    user: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
) -> dict:
    if not payload.session_id:
        raise HTTPException(status_code=400, detail="session_id_required")
    try:
        return save_chat_feedback(
            _identity(user, payload.session_id),
            trace_id=payload.trace_id or "",
            rating=payload.rating,
            comment=payload.comment,
            idempotency_key=payload.idempotency_key,
        )
    except (MemoryPersistenceError, MemoryNotFoundError, MemoryConflictError) as exc:
        _raise_memory_http(exc)
        raise AssertionError("unreachable")


@router.post("/api/ai/feedback")
def ai_answer_feedback(
    payload: AnswerFeedbackRequest,
    user: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
) -> dict:
    if not payload.session_id:
        raise HTTPException(status_code=400, detail="session_id_required")
    try:
        return save_answer_feedback(
            _identity(user, payload.session_id),
            trace_id=payload.trace_id or "",
            question=payload.question,
            answer=payload.answer,
            feedback_type=payload.feedback_type,
            feedback_comment=payload.feedback_comment,
            idempotency_key=payload.idempotency_key,
        )
    except (MemoryPersistenceError, MemoryNotFoundError, MemoryConflictError) as exc:
        _raise_memory_http(exc)
        raise AssertionError("unreachable")


@router.get("/api/ai/chat/sessions")
def ai_chat_sessions(
    user: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
    page: int = 1,
    page_size: int = 50,
) -> dict:
    try:
        result = list_chat_sessions(_identity(user), page=page, page_size=page_size)
        return {"sessions": result["items"], **result}
    except MemoryPersistenceError as exc:
        _raise_memory_http(exc)
        raise AssertionError("unreachable")


@router.get("/api/ai/chat/sessions/{session_id}")
def ai_chat_session(
    session_id: str,
    user: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
) -> dict:
    try:
        return get_chat_session(_identity(user, session_id))
    except (MemoryPersistenceError, MemoryNotFoundError, MemoryConflictError) as exc:
        _raise_memory_http(exc)
        raise AssertionError("unreachable")


@router.patch("/api/ai/chat/sessions/{session_id}")
def ai_update_chat_session(
    session_id: str,
    user: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
    payload: dict[str, Any] = Body(...),
) -> dict:
    if set(payload) - {"title"}:
        raise HTTPException(status_code=400, detail="identity_override_forbidden")
    title = str(payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title_required")
    try:
        return update_chat_session(_identity(user, session_id), title=title)
    except (MemoryPersistenceError, MemoryNotFoundError, MemoryConflictError) as exc:
        _raise_memory_http(exc)
        raise AssertionError("unreachable")


@router.delete("/api/ai/chat/sessions/{session_id}")
def ai_delete_chat_session(
    session_id: str,
    user: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
) -> dict:
    try:
        delete_chat_session(_identity(user, session_id))
        return {"ok": True}
    except (MemoryPersistenceError, MemoryNotFoundError, MemoryConflictError) as exc:
        _raise_memory_http(exc)
        raise AssertionError("unreachable")


@router.get("/api/ai/insights")
def ai_insights(_: Annotated[CurrentUser, Depends(require_permission("assistant:use"))]) -> dict:
    return generate_ai_insights()


@router.get("/api/ai/traces")
def ai_traces(
    user: Annotated[CurrentUser, Depends(require_permission("trace:read"))],
    limit: int = 50,
    session_id: str | None = None,
) -> dict:
    from ....repositories.ai_trace_repository import list_ai_traces

    return {"traces": list_ai_traces(_identity(user), limit=limit, session_id=session_id)}


@router.get("/api/ai/traces/{trace_id}")
def ai_trace_detail(
    trace_id: str,
    user: Annotated[CurrentUser, Depends(require_permission("trace:read"))],
) -> dict:
    from fastapi import HTTPException
    from ....repositories.ai_trace_repository import get_ai_trace

    trace = get_ai_trace(_identity(user), trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace 不存在")
    return trace

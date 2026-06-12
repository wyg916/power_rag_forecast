from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ....core.security import CurrentUser, require_permission
from ....repositories.audit_repository import write_audit_log
from ....platform_services import answer_chat, generate_ai_insights, get_chat_session, list_chat_sessions
from ....schemas import AgentAnalyzeRequest, AnswerFeedbackRequest, ChatFeedbackRequest, ChatRequest
from backend.app.ai_assistant.service import answer_chat_accurate


router = APIRouter()


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
    return answer_chat(
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
    return answer_chat_accurate(
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
    )


@router.post("/api/ai/chat/feedback")
def ai_chat_feedback(
    payload: ChatFeedbackRequest,
    _: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
) -> dict:
    from ....ai.chat_memory import save_chat_feedback

    return save_chat_feedback(
        session_id=payload.session_id or "",
        trace_id=payload.trace_id or "",
        rating=payload.rating,
        comment=payload.comment,
    )


@router.post("/api/ai/feedback")
def ai_answer_feedback(
    payload: AnswerFeedbackRequest,
    _: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
) -> dict:
    from ....ai.chat_memory import save_answer_feedback

    return save_answer_feedback(
        session_id=payload.session_id or "",
        trace_id=payload.trace_id or "",
        question=payload.question,
        answer=payload.answer,
        feedback_type=payload.feedback_type,
        feedback_comment=payload.feedback_comment,
    )


@router.get("/api/ai/chat/sessions")
def ai_chat_sessions(_: Annotated[CurrentUser, Depends(require_permission("assistant:use"))]) -> dict:
    return {"sessions": list_chat_sessions()}


@router.get("/api/ai/chat/sessions/{session_id}")
def ai_chat_session(
    session_id: str,
    _: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
) -> dict:
    return get_chat_session(session_id)


@router.get("/api/ai/insights")
def ai_insights(_: Annotated[CurrentUser, Depends(require_permission("assistant:use"))]) -> dict:
    return generate_ai_insights()


@router.get("/api/ai/traces")
def ai_traces(
    _: Annotated[CurrentUser, Depends(require_permission("trace:read"))],
    limit: int = 50,
    session_id: str | None = None,
) -> dict:
    from ....repositories.ai_trace_repository import list_ai_traces

    return {"traces": list_ai_traces(limit=limit, session_id=session_id)}


@router.get("/api/ai/traces/{trace_id}")
def ai_trace_detail(
    trace_id: str,
    _: Annotated[CurrentUser, Depends(require_permission("trace:read"))],
) -> dict:
    from fastapi import HTTPException
    from ....repositories.ai_trace_repository import get_ai_trace

    trace = get_ai_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace 不存在")
    return trace

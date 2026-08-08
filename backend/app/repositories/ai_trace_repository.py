from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.app.ai.identity_context import IdentityContext

from .base import dumps_json, mapping_dict, mapping_list, postgres_engine


def _engine():
    engine = postgres_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL trace store unavailable")
    return engine


def _identity(identity: IdentityContext, *, require_session: bool = False) -> dict[str, Any]:
    identity.require_valid(require_session=require_session)
    return {
        "tenant_id": identity.tenant_id,
        "workspace_id": identity.workspace_id,
        "user_id": identity.user_id,
        "role_ids": dumps_json(list(identity.role_ids)),
        "agent_id": identity.agent_id,
        "session_id": identity.session_id,
        "run_id": identity.run_id,
    }


def save_ai_trace(
    identity: IdentityContext,
    *,
    trace_id: str,
    question: str,
    intent: str,
    answer: str,
    tools: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    guard_result: dict[str, Any],
    trace_payload: dict[str, Any],
) -> bool:
    if not trace_id:
        raise ValueError("trace_id is required")
    params = _identity(identity, require_session=True)
    rag_context = trace_payload.get("rag_context") or [
        item for item in evidence if item.get("chunk_id") or str(item.get("source") or "").startswith("kb_")
    ]
    with _engine().begin() as connection:
        row = connection.execute(
            text(
                """
                INSERT INTO ai_traces (
                    trace_id, tenant_id, workspace_id, user_id, role_ids, agent_id,
                    session_id, run_id, question, intent, answer, tools_json,
                    evidence_json, guard_result_json, trace_json, llm_output_json,
                    rag_context_json, duration_ms
                ) VALUES (
                    :trace_id, :tenant_id, :workspace_id, :user_id,
                    CAST(:role_ids AS jsonb), :agent_id, :session_id, :run_id,
                    :question, :intent, :answer, CAST(:tools_json AS jsonb),
                    CAST(:evidence_json AS jsonb), CAST(:guard_result_json AS jsonb),
                    CAST(:trace_json AS jsonb), CAST(:llm_output_json AS jsonb),
                    CAST(:rag_context_json AS jsonb), :duration_ms
                )
                ON CONFLICT (trace_id) DO UPDATE SET
                    answer = EXCLUDED.answer,
                    tools_json = EXCLUDED.tools_json,
                    evidence_json = EXCLUDED.evidence_json,
                    guard_result_json = EXCLUDED.guard_result_json,
                    trace_json = EXCLUDED.trace_json,
                    llm_output_json = EXCLUDED.llm_output_json,
                    rag_context_json = EXCLUDED.rag_context_json,
                    duration_ms = EXCLUDED.duration_ms,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ai_traces.tenant_id = EXCLUDED.tenant_id
                  AND ai_traces.workspace_id = EXCLUDED.workspace_id
                  AND ai_traces.user_id = EXCLUDED.user_id
                  AND ai_traces.agent_id = EXCLUDED.agent_id
                RETURNING trace_id
                """
            ),
            {
                **params,
                "trace_id": trace_id,
                "question": question,
                "intent": intent,
                "answer": answer,
                "tools_json": dumps_json(tools),
                "evidence_json": dumps_json(evidence),
                "guard_result_json": dumps_json(guard_result),
                "trace_json": dumps_json(trace_payload),
                "llm_output_json": dumps_json({"answer": answer, "llm_used": trace_payload.get("llm_used")}),
                "rag_context_json": dumps_json(rag_context),
                "duration_ms": trace_payload.get("duration_ms"),
            },
        ).first()
    if not row:
        raise RuntimeError("trace id belongs to another identity")
    return True


def get_ai_trace(identity: IdentityContext, trace_id: str) -> dict[str, Any] | None:
    with _engine().connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT trace_id, session_id, run_id, question, intent, answer,
                       tools_json, evidence_json, guard_result_json, trace_json,
                       llm_output_json, rag_context_json, duration_ms,
                       created_at, updated_at
                FROM ai_traces
                WHERE trace_id = :trace_id AND tenant_id = :tenant_id
                  AND workspace_id = :workspace_id AND user_id = :user_id
                  AND agent_id = :agent_id
                LIMIT 1
                """
            ),
            {**_identity(identity), "trace_id": trace_id},
        ).mappings().first()
    return mapping_dict(row) if row else None


def list_ai_traces(
    identity: IdentityContext,
    *,
    limit: int = 50,
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {**_identity(identity), "limit": max(1, min(int(limit or 50), 200))}
    where_session = ""
    if session_id:
        where_session = "AND session_id = :filter_session_id"
        params["filter_session_id"] = session_id
    with _engine().connect() as connection:
        rows = connection.execute(
            text(
                f"""
                SELECT trace_id, session_id, run_id, question, intent, tools_json,
                       evidence_json, guard_result_json, rag_context_json,
                       duration_ms, created_at, updated_at
                FROM ai_traces
                WHERE tenant_id = :tenant_id AND workspace_id = :workspace_id
                  AND user_id = :user_id AND agent_id = :agent_id
                  {where_session}
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
    return mapping_list(rows)

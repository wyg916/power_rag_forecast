from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .base import dumps_json, mapping_dict, mapping_list, postgres_engine


def save_ai_trace(
    *,
    trace_id: str,
    session_id: str | None,
    question: str,
    intent: str,
    answer: str,
    tools: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    guard_result: dict[str, Any],
    trace_payload: dict[str, Any],
) -> bool:
    engine = postgres_engine()
    if engine is None or not trace_id:
        return False
    try:
        duration_ms = trace_payload.get("duration_ms")
        rag_context = trace_payload.get("rag_context") or [
            item for item in evidence if item.get("chunk_id") or str(item.get("source") or "").startswith("kb_")
        ]
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO ai_traces (
                        trace_id, session_id, question, intent, answer,
                        tools_json, evidence_json, guard_result_json, trace_json,
                        llm_output_json, rag_context_json, duration_ms
                    )
                    VALUES (
                        :trace_id, :session_id, :question, :intent, :answer,
                        CAST(:tools_json AS jsonb), CAST(:evidence_json AS jsonb),
                        CAST(:guard_result_json AS jsonb), CAST(:trace_json AS jsonb),
                        CAST(:llm_output_json AS jsonb), CAST(:rag_context_json AS jsonb),
                        :duration_ms
                    )
                    ON CONFLICT (trace_id) DO UPDATE SET
                        session_id = EXCLUDED.session_id,
                        question = EXCLUDED.question,
                        intent = EXCLUDED.intent,
                        answer = EXCLUDED.answer,
                        tools_json = EXCLUDED.tools_json,
                        evidence_json = EXCLUDED.evidence_json,
                        guard_result_json = EXCLUDED.guard_result_json,
                        trace_json = EXCLUDED.trace_json,
                        llm_output_json = EXCLUDED.llm_output_json,
                        rag_context_json = EXCLUDED.rag_context_json,
                        duration_ms = EXCLUDED.duration_ms,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    "trace_id": trace_id,
                    "session_id": session_id,
                    "question": question,
                    "intent": intent,
                    "answer": answer,
                    "tools_json": dumps_json(tools),
                    "evidence_json": dumps_json(evidence),
                    "guard_result_json": dumps_json(guard_result),
                    "trace_json": dumps_json(trace_payload),
                    "llm_output_json": dumps_json({"answer": answer, "llm_used": trace_payload.get("llm_used")}),
                    "rag_context_json": dumps_json(rag_context),
                    "duration_ms": duration_ms,
                },
            )
        return True
    except Exception:
        return False


def get_ai_trace(trace_id: str) -> dict[str, Any] | None:
    engine = postgres_engine()
    if engine is None:
        return None
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT trace_id, session_id, question, intent, answer, tools_json,
                           evidence_json, guard_result_json, trace_json,
                           llm_output_json, rag_context_json, duration_ms,
                           created_at, updated_at
                    FROM ai_traces
                    WHERE trace_id = :trace_id
                    LIMIT 1
                    """
                ),
                {"trace_id": trace_id},
            ).mappings().first()
    except Exception:
        return None
    return mapping_dict(row) if row else None


def list_ai_traces(limit: int = 50, session_id: str | None = None) -> list[dict[str, Any]]:
    engine = postgres_engine()
    if engine is None:
        return []
    params: dict[str, Any] = {"limit": max(1, min(int(limit or 50), 200))}
    where = ""
    if session_id:
        where = "WHERE session_id = :session_id"
        params["session_id"] = session_id
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT trace_id, session_id, question, intent, tools_json,
                           evidence_json, guard_result_json, rag_context_json,
                           duration_ms, created_at, updated_at
                    FROM ai_traces
                    {where}
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
    except Exception:
        return []
    return mapping_list(rows)

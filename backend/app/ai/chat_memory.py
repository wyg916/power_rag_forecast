from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from ..data_access import jsonable
from ..repositories.base import postgres_engine
from .identity_context import IdentityContext


class MemoryPersistenceError(RuntimeError):
    pass


class MemoryNotFoundError(LookupError):
    pass


class MemoryConflictError(RuntimeError):
    pass


def _engine() -> Engine:
    engine = postgres_engine()
    if engine is None:
        raise MemoryPersistenceError("PostgreSQL memory store unavailable")
    return engine


def _identity_params(identity: IdentityContext, *, require_session: bool = True) -> dict[str, Any]:
    identity.require_valid(require_session=require_session)
    return {
        "tenant_id": identity.tenant_id,
        "workspace_id": identity.workspace_id,
        "user_id": identity.user_id,
        "role_ids": json.dumps(list(identity.role_ids), ensure_ascii=False),
        "agent_id": identity.agent_id,
        "session_id": identity.session_id,
        "run_id": identity.run_id,
    }


def _require_owned_session(connection: Connection, identity: IdentityContext) -> None:
    row = connection.execute(
        text(
            """
            SELECT 1 FROM ai_chat_sessions
            WHERE tenant_id = :tenant_id AND workspace_id = :workspace_id
              AND user_id = :user_id AND agent_id = :agent_id
              AND session_id = :session_id
            """
        ),
        _identity_params(identity),
    ).first()
    if not row:
        raise MemoryNotFoundError("assistant session not found")


def assert_session_available(identity: IdentityContext) -> None:
    """Allow a new id or an id owned by this identity; conceal foreign ownership."""
    try:
        with _engine().connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT tenant_id, workspace_id, user_id, agent_id
                    FROM ai_chat_sessions WHERE session_id = :session_id
                    """
                ),
                {"session_id": identity.session_id},
            ).mappings().first()
        if row and (
            row["tenant_id"], row["workspace_id"], row["user_id"], row["agent_id"]
        ) != (
            identity.tenant_id, identity.workspace_id, identity.user_id, identity.agent_id
        ):
            raise MemoryNotFoundError("assistant session not found")
    except MemoryNotFoundError:
        raise
    except Exception as exc:
        raise MemoryPersistenceError("session ownership check failed") from exc


def _upsert_session(connection: Connection, identity: IdentityContext, title: str) -> None:
    params = {**_identity_params(identity), "title": title[:255]}
    row = connection.execute(
        text(
            """
            INSERT INTO ai_chat_sessions (
                tenant_id, workspace_id, user_id, role_ids, agent_id,
                session_id, run_id, title, created_at, updated_at
            ) VALUES (
                :tenant_id, :workspace_id, :user_id, CAST(:role_ids AS jsonb), :agent_id,
                :session_id, :run_id, :title, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (session_id) DO UPDATE SET
                role_ids = EXCLUDED.role_ids,
                run_id = EXCLUDED.run_id,
                title = COALESCE(ai_chat_sessions.title, EXCLUDED.title),
                updated_at = CURRENT_TIMESTAMP
            WHERE ai_chat_sessions.tenant_id = EXCLUDED.tenant_id
              AND ai_chat_sessions.workspace_id = EXCLUDED.workspace_id
              AND ai_chat_sessions.user_id = EXCLUDED.user_id
              AND ai_chat_sessions.agent_id = EXCLUDED.agent_id
            RETURNING id
            """
        ),
        params,
    ).first()
    if not row:
        raise MemoryConflictError("session id belongs to another identity")


def save_assistant_turn(
    *,
    identity: IdentityContext,
    question: str,
    answer: str,
    intent: str,
    evidence: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
    state: Any,
    trace_id: str,
    trace_payload: dict[str, Any],
    guard_result: dict[str, Any],
) -> None:
    """Persist one assistant turn atomically and idempotently."""
    if not trace_id:
        raise MemoryPersistenceError("trace_id is required for idempotent persistence")
    params = _identity_params(identity)
    try:
        with _engine().begin() as connection:
            _upsert_session(connection, identity, question)
            for role, content, item_evidence in (
                ("user", question, []),
                ("assistant", answer, evidence),
            ):
                connection.execute(
                    text(
                        """
                        INSERT INTO ai_chat_messages (
                            tenant_id, workspace_id, user_id, role_ids, agent_id,
                            session_id, run_id, message_key, role, content, evidence_json, created_at
                        ) VALUES (
                            :tenant_id, :workspace_id, :user_id, CAST(:role_ids AS jsonb), :agent_id,
                            :session_id, :run_id, :message_key, :role, :content,
                            CAST(:evidence_json AS jsonb), CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (
                            tenant_id, workspace_id, user_id, agent_id, session_id, message_key
                        ) WHERE message_key IS NOT NULL DO NOTHING
                        """
                    ),
                    {
                        **params,
                        "message_key": f"{trace_id}:{role}",
                        "role": role,
                        "content": content,
                        "evidence_json": json.dumps(jsonable(item_evidence), ensure_ascii=False),
                    },
                )

            for index, call in enumerate(tool_calls):
                connection.execute(
                    text(
                        """
                        INSERT INTO ai_tool_call_logs (
                            tenant_id, workspace_id, user_id, role_ids, agent_id,
                            session_id, run_id, tool_call_key, tool_name, input_json,
                            output_json, success, error_message, created_at
                        ) VALUES (
                            :tenant_id, :workspace_id, :user_id, CAST(:role_ids AS jsonb), :agent_id,
                            :session_id, :run_id, :tool_call_key, :tool_name,
                            CAST(:input_json AS jsonb), CAST(:output_json AS jsonb),
                            :success, :error_message, CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (
                            tenant_id, workspace_id, user_id, agent_id, session_id, tool_call_key
                        ) WHERE tool_call_key IS NOT NULL DO NOTHING
                        """
                    ),
                    {
                        **params,
                        "tool_call_key": f"{trace_id}:{index}",
                        "tool_name": str(call.get("tool_name") or "unknown"),
                        "input_json": json.dumps(jsonable(call.get("input") or {}), ensure_ascii=False),
                        "output_json": json.dumps(jsonable(call.get("output") or {}), ensure_ascii=False),
                        "success": bool(call.get("success")),
                        "error_message": call.get("error_message"),
                    },
                )

            state_record = jsonable(state.__dict__)
            state_record["last_focus_time"] = state_record.get("last_focus_time") or None
            state_row = connection.execute(
                text(
                    """
                    INSERT INTO ai_conversation_state (
                        tenant_id, workspace_id, user_id, role_ids, agent_id,
                        session_id, run_id, last_intent, last_topic, last_focus_time,
                        last_focus_metric, last_focus_value, last_run_id,
                        last_answer_summary, updated_at
                    ) VALUES (
                        :tenant_id, :workspace_id, :user_id, CAST(:role_ids AS jsonb), :agent_id,
                        :session_id, :run_id, :last_intent, :last_topic, :last_focus_time,
                        :last_focus_metric, :last_focus_value, :last_run_id,
                        :last_answer_summary, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (session_id) DO UPDATE SET
                        role_ids = EXCLUDED.role_ids,
                        run_id = EXCLUDED.run_id,
                        last_intent = EXCLUDED.last_intent,
                        last_topic = EXCLUDED.last_topic,
                        last_focus_time = EXCLUDED.last_focus_time,
                        last_focus_metric = EXCLUDED.last_focus_metric,
                        last_focus_value = EXCLUDED.last_focus_value,
                        last_run_id = EXCLUDED.last_run_id,
                        last_answer_summary = EXCLUDED.last_answer_summary,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE ai_conversation_state.tenant_id = EXCLUDED.tenant_id
                      AND ai_conversation_state.workspace_id = EXCLUDED.workspace_id
                      AND ai_conversation_state.user_id = EXCLUDED.user_id
                      AND ai_conversation_state.agent_id = EXCLUDED.agent_id
                    RETURNING id
                    """
                ),
                {**params, **state_record},
            ).first()
            if not state_row:
                raise MemoryConflictError("conversation state belongs to another identity")

            trace_row = connection.execute(
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
                    "tools_json": json.dumps(jsonable(tool_calls), ensure_ascii=False),
                    "evidence_json": json.dumps(jsonable(evidence), ensure_ascii=False),
                    "guard_result_json": json.dumps(jsonable(guard_result), ensure_ascii=False),
                    "trace_json": json.dumps(jsonable(trace_payload), ensure_ascii=False),
                    "llm_output_json": json.dumps(
                        {"answer": answer, "llm_used": trace_payload.get("llm_used")}, ensure_ascii=False
                    ),
                    "rag_context_json": json.dumps(
                        [item for item in evidence if item.get("chunk_id") or str(item.get("source") or "").startswith("kb_")],
                        ensure_ascii=False,
                    ),
                    "duration_ms": trace_payload.get("duration_ms"),
                },
            ).first()
            if not trace_row:
                raise MemoryConflictError("trace id belongs to another identity")
    except (MemoryConflictError, MemoryNotFoundError):
        raise
    except Exception as exc:
        raise MemoryPersistenceError("assistant turn persistence failed") from exc


def _feedback_key(kind: str, identity: IdentityContext, values: list[str]) -> str:
    raw = "|".join([kind, identity.tenant_id, identity.workspace_id, identity.user_id, *values])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _verify_trace(connection: Connection, identity: IdentityContext, trace_id: str) -> None:
    if not trace_id:
        return
    row = connection.execute(
        text(
            """
            SELECT 1 FROM ai_traces
            WHERE trace_id = :trace_id AND tenant_id = :tenant_id
              AND workspace_id = :workspace_id AND user_id = :user_id
              AND agent_id = :agent_id AND session_id = :session_id
            """
        ),
        {**_identity_params(identity), "trace_id": trace_id},
    ).first()
    if not row:
        raise MemoryNotFoundError("assistant trace not found")


def save_chat_feedback(
    identity: IdentityContext,
    *,
    trace_id: str,
    rating: str,
    comment: str = "",
    idempotency_key: str = "",
) -> dict[str, Any]:
    key = idempotency_key or _feedback_key("chat", identity, [trace_id, rating, comment])
    try:
        with _engine().begin() as connection:
            _require_owned_session(connection, identity)
            _verify_trace(connection, identity, trace_id)
            row = connection.execute(
                text(
                    """
                    INSERT INTO ai_chat_feedback (
                        tenant_id, workspace_id, user_id, role_ids, agent_id,
                        session_id, run_id, trace_id, rating, comment, idempotency_key, created_at
                    ) VALUES (
                        :tenant_id, :workspace_id, :user_id, CAST(:role_ids AS jsonb), :agent_id,
                        :session_id, :run_id, :trace_id, :rating, :comment, :idempotency_key,
                        CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (tenant_id, workspace_id, user_id, agent_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL DO NOTHING
                    RETURNING id
                    """
                ),
                {**_identity_params(identity), "trace_id": trace_id, "rating": rating, "comment": comment, "idempotency_key": key},
            ).first()
        return {"ok": True, "created": bool(row), "session_id": identity.session_id, "trace_id": trace_id}
    except (MemoryNotFoundError, MemoryConflictError):
        raise
    except Exception as exc:
        raise MemoryPersistenceError("chat feedback persistence failed") from exc


def save_answer_feedback(
    identity: IdentityContext,
    *,
    trace_id: str,
    question: str = "",
    answer: str = "",
    feedback_type: str = "answer_mismatch",
    feedback_comment: str = "",
    idempotency_key: str = "",
) -> dict[str, Any]:
    key = idempotency_key or _feedback_key(
        "answer", identity, [trace_id, feedback_type, feedback_comment, question, answer]
    )
    try:
        with _engine().begin() as connection:
            _require_owned_session(connection, identity)
            _verify_trace(connection, identity, trace_id)
            row = connection.execute(
                text(
                    """
                    INSERT INTO ai_answer_feedback (
                        tenant_id, workspace_id, user_id, role_ids, agent_id,
                        session_id, run_id, trace_id, question, answer, feedback_type,
                        feedback_comment, idempotency_key, created_at
                    ) VALUES (
                        :tenant_id, :workspace_id, :user_id, CAST(:role_ids AS jsonb), :agent_id,
                        :session_id, :run_id, :trace_id, :question, :answer, :feedback_type,
                        :feedback_comment, :idempotency_key, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (tenant_id, workspace_id, user_id, agent_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    **_identity_params(identity),
                    "trace_id": trace_id,
                    "question": question,
                    "answer": answer,
                    "feedback_type": feedback_type,
                    "feedback_comment": feedback_comment,
                    "idempotency_key": key,
                },
            ).first()
        return {"ok": True, "created": bool(row), "session_id": identity.session_id, "trace_id": trace_id}
    except (MemoryNotFoundError, MemoryConflictError):
        raise
    except Exception as exc:
        raise MemoryPersistenceError("answer feedback persistence failed") from exc


def list_chat_sessions(identity: IdentityContext, *, page: int = 1, page_size: int = 50) -> dict[str, Any]:
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 50), 100))
    params = {**_identity_params(identity, require_session=False), "limit": page_size, "offset": (page - 1) * page_size}
    try:
        with _engine().connect() as connection:
            total = connection.execute(
                text(
                    """
                    SELECT count(*) FROM ai_chat_sessions
                    WHERE tenant_id = :tenant_id AND workspace_id = :workspace_id
                      AND user_id = :user_id AND agent_id = :agent_id
                    """
                ),
                params,
            ).scalar_one()
            rows = connection.execute(
                text(
                    """
                    SELECT session_id, title, run_id, created_at, updated_at
                    FROM ai_chat_sessions
                    WHERE tenant_id = :tenant_id AND workspace_id = :workspace_id
                      AND user_id = :user_id AND agent_id = :agent_id
                    ORDER BY updated_at DESC, id DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            ).mappings().all()
        return {"items": [jsonable(dict(row)) for row in rows], "total": int(total), "page": page, "page_size": page_size}
    except Exception as exc:
        raise MemoryPersistenceError("session list failed") from exc


def get_chat_session(identity: IdentityContext) -> dict[str, Any]:
    try:
        with _engine().connect() as connection:
            _require_owned_session(connection, identity)
            rows = connection.execute(
                text(
                    """
                    SELECT role, content, evidence_json, run_id, created_at
                    FROM ai_chat_messages
                    WHERE tenant_id = :tenant_id AND workspace_id = :workspace_id
                      AND user_id = :user_id AND agent_id = :agent_id
                      AND session_id = :session_id
                    ORDER BY created_at ASC, id ASC
                    """
                ),
                _identity_params(identity),
            ).mappings().all()
        return {"session_id": identity.session_id, "messages": [jsonable(dict(row)) for row in rows]}
    except MemoryNotFoundError:
        raise
    except Exception as exc:
        raise MemoryPersistenceError("session detail failed") from exc


def update_chat_session(identity: IdentityContext, *, title: str) -> dict[str, Any]:
    try:
        with _engine().begin() as connection:
            row = connection.execute(
                text(
                    """
                    UPDATE ai_chat_sessions SET title = :title, updated_at = CURRENT_TIMESTAMP
                    WHERE tenant_id = :tenant_id AND workspace_id = :workspace_id
                      AND user_id = :user_id AND agent_id = :agent_id
                      AND session_id = :session_id
                    RETURNING session_id, title, run_id, created_at, updated_at
                    """
                ),
                {**_identity_params(identity), "title": title[:255]},
            ).mappings().first()
        if not row:
            raise MemoryNotFoundError("assistant session not found")
        return jsonable(dict(row))
    except MemoryNotFoundError:
        raise
    except Exception as exc:
        raise MemoryPersistenceError("session update failed") from exc


def delete_chat_session(identity: IdentityContext) -> None:
    params = _identity_params(identity)
    try:
        with _engine().begin() as connection:
            _require_owned_session(connection, identity)
            for table in (
                "ai_chat_feedback",
                "ai_answer_feedback",
                "ai_tool_call_logs",
                "ai_chat_messages",
                "ai_conversation_state",
                "ai_traces",
            ):
                connection.execute(
                    text(
                        f"""
                        DELETE FROM {table}
                        WHERE tenant_id = :tenant_id AND workspace_id = :workspace_id
                          AND user_id = :user_id AND agent_id = :agent_id
                          AND session_id = :session_id
                        """
                    ),
                    params,
                )
            connection.execute(
                text(
                    """
                    DELETE FROM ai_chat_sessions
                    WHERE tenant_id = :tenant_id AND workspace_id = :workspace_id
                      AND user_id = :user_id AND agent_id = :agent_id
                      AND session_id = :session_id
                    """
                ),
                params,
            )
    except MemoryNotFoundError:
        raise
    except Exception as exc:
        raise MemoryPersistenceError("session delete failed") from exc

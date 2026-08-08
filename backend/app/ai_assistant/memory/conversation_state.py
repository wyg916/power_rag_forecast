from __future__ import annotations

import json

from sqlalchemy import text

from ...ai.chat_memory import MemoryConflictError, MemoryPersistenceError
from ...ai.identity_context import IdentityContext
from ...repositories.base import postgres_engine
from ..schemas import ConversationState


def get_conversation_state(identity: IdentityContext) -> ConversationState | None:
    identity.require_valid(require_session=True)
    engine = postgres_engine()
    if engine is None:
        raise MemoryPersistenceError("PostgreSQL conversation state unavailable")
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT session_id, last_intent, last_topic, last_focus_time,
                           last_focus_metric, last_focus_value, last_run_id,
                           last_answer_summary
                    FROM ai_conversation_state
                    WHERE tenant_id = :tenant_id AND workspace_id = :workspace_id
                      AND user_id = :user_id AND agent_id = :agent_id
                      AND session_id = :session_id
                    LIMIT 1
                    """
                ),
                {
                    "tenant_id": identity.tenant_id,
                    "workspace_id": identity.workspace_id,
                    "user_id": identity.user_id,
                    "agent_id": identity.agent_id,
                    "session_id": identity.session_id,
                },
            ).mappings().first()
    except Exception as exc:
        raise MemoryPersistenceError("conversation state read failed") from exc
    if not row:
        return None
    data = dict(row)
    if data.get("last_focus_time"):
        data["last_focus_time"] = str(data["last_focus_time"])
    return ConversationState(**data)


def save_conversation_state(identity: IdentityContext, state: ConversationState) -> None:
    identity.require_valid(require_session=True)
    if state.session_id != identity.session_id:
        raise MemoryConflictError("conversation state session mismatch")
    engine = postgres_engine()
    if engine is None:
        raise MemoryPersistenceError("PostgreSQL conversation state unavailable")
    params = {
        "tenant_id": identity.tenant_id,
        "workspace_id": identity.workspace_id,
        "user_id": identity.user_id,
        "role_ids": json.dumps(list(identity.role_ids), ensure_ascii=False),
        "agent_id": identity.agent_id,
        "session_id": identity.session_id,
        "run_id": identity.run_id,
        **state.__dict__,
    }
    params["last_focus_time"] = params.get("last_focus_time") or None
    try:
        with engine.begin() as connection:
            row = connection.execute(
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
                params,
            ).first()
        if not row:
            raise MemoryConflictError("conversation state belongs to another identity")
    except MemoryConflictError:
        raise
    except Exception as exc:
        raise MemoryPersistenceError("conversation state persistence failed") from exc

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from ..config import project_config, project_paths
from ..data_access import database_engine, jsonable


def _write_local_json(name: str, payload: Any) -> None:
    paths = project_paths()
    paths.current_dir.mkdir(parents=True, exist_ok=True)
    (paths.current_dir / name).write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def save_chat_exchange(
    session_id: str,
    question: str,
    answer: str,
    intent: str,
    evidence: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
    user_role: str,
    scenario: str,
    trace_id: str = "",
) -> None:
    engine = database_engine()
    if engine is None:
        return
    try:
        from database_utils import apply_database_migrations

        apply_database_migrations(project_config())
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO ai_chat_sessions (session_id, user_id, title, created_at, updated_at)
                    VALUES (:session_id, 'web_user', :title, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP, title = COALESCE(title, VALUES(title))
                    """
                ),
                {"session_id": session_id, "title": question[:120]},
            )
            for role, content, ev in [
                ("user", question, []),
                ("assistant", answer, evidence),
            ]:
                conn.execute(
                    text(
                        """
                            INSERT INTO ai_chat_messages (session_id, role, content, evidence_json, created_at)
                            VALUES (:session_id, :role, :content, :evidence_json, CURRENT_TIMESTAMP)
                        """
                    ),
                    {
                        "session_id": session_id,
                        "role": role,
                        "content": content,
                        "evidence_json": json.dumps(jsonable(ev), ensure_ascii=False),
                    },
                )
            for call in tool_calls:
                conn.execute(
                    text(
                        """
                        INSERT INTO ai_tool_call_logs (session_id, tool_name, input_json, output_json, success, error_message, created_at)
                        VALUES (:session_id, :tool_name, :input_json, :output_json, :success, :error_message, CURRENT_TIMESTAMP)
                        """
                    ),
                    {
                        "session_id": session_id,
                        "tool_name": call.get("tool_name"),
                        "input_json": json.dumps(jsonable(call.get("input") or {}), ensure_ascii=False),
                        "output_json": json.dumps(jsonable(call.get("output") or {}), ensure_ascii=False),
                        "success": bool(call.get("success")),
                        "error_message": call.get("error_message"),
                    },
                )
    except Exception:
        return


def save_chat_feedback(session_id: str, trace_id: str, rating: str, comment: str = "") -> dict[str, Any]:
    record = {
        "session_id": session_id,
        "trace_id": trace_id,
        "rating": rating,
        "comment": comment,
    }
    engine = database_engine()
    if engine is not None:
        try:
            from database_utils import apply_database_migrations

            apply_database_migrations(project_config())
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO ai_chat_feedback (session_id, trace_id, rating, comment, created_at)
                        VALUES (:session_id, :trace_id, :rating, :comment, CURRENT_TIMESTAMP)
                        """
                    ),
                    record,
                )
            return {"ok": True, **record}
        except Exception:
            pass
    try:
        _write_local_json("ai_chat_feedback_latest.json", record)
    except Exception:
        pass
    return {"ok": True, **record, "source": "local"}


def save_answer_feedback(
    session_id: str,
    trace_id: str,
    question: str = "",
    answer: str = "",
    feedback_type: str = "answer_mismatch",
    feedback_comment: str = "",
) -> dict[str, Any]:
    record = {
        "session_id": session_id,
        "trace_id": trace_id,
        "question": question,
        "answer": answer,
        "feedback_type": feedback_type,
        "feedback_comment": feedback_comment,
    }
    engine = database_engine()
    if engine is not None:
        try:
            from database_utils import apply_database_migrations

            apply_database_migrations(project_config())
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO ai_answer_feedback
                            (session_id, trace_id, question, answer, feedback_type, feedback_comment, created_at)
                        VALUES
                            (:session_id, :trace_id, :question, :answer, :feedback_type, :feedback_comment, CURRENT_TIMESTAMP)
                        """
                    ),
                    record,
                )
            return {"ok": True, **record}
        except Exception:
            pass
    try:
        _write_local_json("ai_answer_feedback_latest.json", record)
    except Exception:
        pass
    return {"ok": True, **record, "source": "local"}

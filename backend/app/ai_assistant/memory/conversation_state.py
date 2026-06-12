from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from ...config import project_config, project_paths
from ...data_access import database_engine, jsonable
from ..schemas import ConversationState


def _local_path() -> Path:
    path = project_paths().current_dir / "ai_conversation_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_local() -> dict[str, Any]:
    path = _local_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_conversation_state(session_id: str | None) -> ConversationState | None:
    if not session_id:
        return None
    engine = database_engine()
    if engine is not None:
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT session_id, last_intent, last_topic, last_focus_time, last_focus_metric,
                               last_focus_value, last_run_id, last_answer_summary
                        FROM ai_conversation_state
                        WHERE session_id = :session_id
                        LIMIT 1
                        """
                    ),
                    {"session_id": session_id},
                ).mappings().fetchone()
                if row:
                    data = dict(row)
                    if data.get("last_focus_time"):
                        data["last_focus_time"] = str(data["last_focus_time"])
                    return ConversationState(**data)
        except Exception:
            pass
    local = _load_local().get(session_id)
    return ConversationState(**local) if local else None


def save_conversation_state(state: ConversationState) -> None:
    engine = database_engine()
    record = jsonable(state.__dict__)
    if engine is not None:
        try:
            from database_utils import apply_database_migrations

            apply_database_migrations(project_config())
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO ai_conversation_state
                            (session_id, last_intent, last_topic, last_focus_time, last_focus_metric,
                             last_focus_value, last_run_id, last_answer_summary, updated_at)
                        VALUES
                            (:session_id, :last_intent, :last_topic, :last_focus_time, :last_focus_metric,
                             :last_focus_value, :last_run_id, :last_answer_summary, CURRENT_TIMESTAMP)
                        ON DUPLICATE KEY UPDATE
                            last_intent = VALUES(last_intent),
                            last_topic = VALUES(last_topic),
                            last_focus_time = VALUES(last_focus_time),
                            last_focus_metric = VALUES(last_focus_metric),
                            last_focus_value = VALUES(last_focus_value),
                            last_run_id = VALUES(last_run_id),
                            last_answer_summary = VALUES(last_answer_summary),
                            updated_at = CURRENT_TIMESTAMP
                        """
                    ),
                    record,
                )
            return
        except Exception:
            pass
    local = _load_local()
    local[state.session_id] = record
    _local_path().write_text(json.dumps(local, ensure_ascii=False, indent=2), encoding="utf-8")

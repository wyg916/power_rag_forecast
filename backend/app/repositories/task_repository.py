from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.app.observability import log_suppressed_exception

from .base import dumps_json, jsonable, loads_json, mapping_dict, mapping_list, postgres_engine


def save_task_record(record: dict[str, Any], status: str | None = None, log_text: str | None = None) -> bool:
    engine = postgres_engine()
    if engine is None:
        return False
    payload = {
        "task_id": record.get("task_id"),
        "run_id": record.get("run_id"),
        "task_name": record.get("task_name") or record.get("kind") or record.get("task_kind"),
        "task_kind": record.get("task_kind") or record.get("kind"),
        "task_type": record.get("task_type") or record.get("task_kind") or record.get("kind"),
        "status": status or record.get("status") or "pending",
        "payload_json": dumps_json(record.get("payload") or {}),
        "command_json": dumps_json(record.get("command") or []),
        "log_path": record.get("log_path") or "",
        "log_text": log_text,
        "started_at": record.get("started_at"),
        "ended_at": record.get("ended_at"),
        "finished_at": record.get("finished_at") or record.get("ended_at"),
        "duration_seconds": record.get("duration_seconds"),
        "returncode": record.get("returncode"),
        "error_message": record.get("error_message") or "",
        "progress": float(record.get("progress") or 0),
        "message": record.get("message") or "",
        "created_by": record.get("created_by") or "system",
        "retry_count": int(record.get("retry_count") or 0),
        "result_ref": record.get("result_ref") or "",
        "metadata_json": dumps_json(record.get("metadata") or record.get("metadata_json") or {}),
        "execution_mode": record.get("execution_mode") or record.get("execution_backend") or "",
        "cancel_requested": bool(record.get("cancel_requested") or False),
        "worker_id": record.get("worker_id") or "",
        "celery_task_id": record.get("celery_task_id") or "",
    }
    if not payload["task_id"]:
        return False
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO task_runs (
                        task_id, run_id, task_name, task_kind, task_type, status, payload_json,
                        started_at, ended_at, finished_at, duration_seconds, error_message,
                        progress, message, created_by, retry_count, result_ref, metadata_json,
                        execution_mode, cancel_requested, worker_id, celery_task_id
                    )
                    VALUES (
                        :task_id, :run_id, :task_name, :task_kind, :task_type, :status,
                        CAST(:payload_json AS jsonb), :started_at, :ended_at, :finished_at,
                        :duration_seconds, :error_message, :progress, :message, :created_by,
                        :retry_count, :result_ref, CAST(:metadata_json AS jsonb),
                        :execution_mode, :cancel_requested, :worker_id, :celery_task_id
                    )
                    ON CONFLICT (task_id) DO UPDATE SET
                        run_id = EXCLUDED.run_id,
                        task_name = EXCLUDED.task_name,
                        task_kind = EXCLUDED.task_kind,
                        task_type = EXCLUDED.task_type,
                        status = EXCLUDED.status,
                        payload_json = EXCLUDED.payload_json,
                        started_at = COALESCE(task_runs.started_at, EXCLUDED.started_at),
                        ended_at = EXCLUDED.ended_at,
                        finished_at = EXCLUDED.finished_at,
                        duration_seconds = EXCLUDED.duration_seconds,
                        error_message = EXCLUDED.error_message,
                        progress = EXCLUDED.progress,
                        message = EXCLUDED.message,
                        created_by = COALESCE(task_runs.created_by, EXCLUDED.created_by),
                        retry_count = EXCLUDED.retry_count,
                        result_ref = EXCLUDED.result_ref,
                        metadata_json = EXCLUDED.metadata_json,
                        execution_mode = COALESCE(NULLIF(EXCLUDED.execution_mode, ''), task_runs.execution_mode),
                        cancel_requested = EXCLUDED.cancel_requested,
                        worker_id = COALESCE(NULLIF(EXCLUDED.worker_id, ''), task_runs.worker_id),
                        celery_task_id = COALESCE(NULLIF(EXCLUDED.celery_task_id, ''), task_runs.celery_task_id),
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                payload,
            )
            updated = conn.execute(
                text(
                    """
                    UPDATE task_logs
                    SET run_id = :run_id,
                        task_name = :task_name,
                        task_kind = :task_kind,
                        status = :status,
                        command_json = CAST(:command_json AS jsonb),
                        log_path = :log_path,
                        log_text = COALESCE(:log_text, log_text),
                        started_at = COALESCE(started_at, :started_at),
                        ended_at = :ended_at,
                        duration_seconds = :duration_seconds,
                        returncode = :returncode,
                        error_message = :error_message,
                        progress = :progress,
                        message = :message,
                        result_ref = :result_ref,
                        metadata_json = CAST(:metadata_json AS jsonb),
                        execution_mode = :execution_mode,
                        cancel_requested = :cancel_requested,
                        worker_id = :worker_id,
                        celery_task_id = :celery_task_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE task_id = :task_id
                    """
                ),
                payload,
            )
            if int(updated.rowcount or 0) == 0:
                conn.execute(
                    text(
                        """
                        INSERT INTO task_logs (
                            task_id, run_id, task_name, task_kind, status,
                            command_json, log_path, log_text, started_at, ended_at,
                            duration_seconds, returncode, error_message
                            , progress, message, result_ref, metadata_json
                            , execution_mode, cancel_requested, worker_id, celery_task_id
                        )
                        VALUES (
                            :task_id, :run_id, :task_name, :task_kind, :status,
                            CAST(:command_json AS jsonb), :log_path, :log_text,
                            :started_at, :ended_at, :duration_seconds, :returncode,
                            :error_message, :progress, :message, :result_ref,
                            CAST(:metadata_json AS jsonb), :execution_mode,
                            :cancel_requested, :worker_id, :celery_task_id
                        )
                        """
                    ),
                    payload,
                )
        return True
    except Exception as exc:
        log_suppressed_exception("repositories.task.save_task_record", exc, task_id=payload.get("task_id"))
        return False


def list_recent_tasks(limit: int = 100) -> list[dict[str, Any]]:
    engine = postgres_engine()
    if engine is None:
        return []
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT task_id, run_id, task_kind AS kind, status, payload_json,
                           started_at, ended_at, finished_at, duration_seconds, error_message,
                           progress, message, created_by, retry_count, result_ref, metadata_json,
                           execution_mode, cancel_requested, worker_id, celery_task_id,
                           updated_at
                    FROM task_runs
                    ORDER BY COALESCE(started_at, updated_at, created_at) DESC
                    LIMIT :limit
                    """
                ),
                {"limit": int(limit)},
            ).mappings().all()
            logs = conn.execute(
                text(
                    """
                    SELECT DISTINCT ON (task_id)
                           task_id, run_id, task_kind AS kind, status, command_json,
                           log_path, started_at, ended_at, duration_seconds,
                           returncode, error_message, progress, message, result_ref,
                           metadata_json, execution_mode, cancel_requested, worker_id,
                           celery_task_id, updated_at
                    FROM task_logs
                    WHERE task_id IS NOT NULL
                    ORDER BY task_id, COALESCE(started_at, updated_at, created_at) DESC
                    LIMIT :limit
                    """
                ),
                {"limit": int(limit)},
            ).mappings().all()
    except Exception as exc:
        log_suppressed_exception("repositories.task.list_recent_tasks", exc, limit=limit)
        return []

    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for row in mapping_list(rows) + mapping_list(logs):
        task_id = str(row.get("task_id") or "")
        if not task_id or task_id in seen:
            continue
        seen.add(task_id)
        row["payload"] = loads_json(row.pop("payload_json", None), default={})
        row["command"] = loads_json(row.pop("command_json", None), default=[])
        row["metadata"] = loads_json(row.pop("metadata_json", None), default={})
        row.setdefault("log_path", "")
        records.append(jsonable(row))
    records.sort(key=lambda item: str(item.get("started_at") or item.get("updated_at") or ""), reverse=True)
    return records[:limit]


def get_task_record(task_id: str) -> dict[str, Any] | None:
    for record in list_recent_tasks(limit=200):
        if record.get("task_id") == task_id:
            return record
    return None


def update_task_runtime_state(
    task_id: str,
    *,
    status: str,
    message: str = "",
    error_message: str = "",
    cancel_requested: bool | None = None,
    retry_count: int | None = None,
    result_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
    finish: bool = False,
) -> bool:
    current = get_task_record(task_id) or {}
    record = dict(current)
    record["task_id"] = task_id
    record["kind"] = current.get("kind") or current.get("task_kind") or current.get("task_name") or "task"
    record["task_name"] = current.get("task_name") or record["kind"]
    record["status"] = status
    record["message"] = message or current.get("message") or status
    record["error_message"] = error_message if error_message else current.get("error_message") or ""
    if cancel_requested is not None:
        record["cancel_requested"] = cancel_requested
    if retry_count is not None:
        record["retry_count"] = retry_count
    if result_ref is not None:
        record["result_ref"] = result_ref
    if metadata is not None:
        merged = dict(current.get("metadata") or {})
        merged.update(metadata)
        record["metadata"] = merged
    if finish:
        from datetime import datetime

        now = datetime.now().isoformat(sep=" ", timespec="seconds")
        record["ended_at"] = current.get("ended_at") or now
        record["finished_at"] = current.get("finished_at") or now
    return save_task_record(record, status=status, log_text=record.get("message") or status)


def task_log_text(task_id: str, tail: int = 4000) -> str | None:
    engine = postgres_engine()
    if engine is None:
        return None
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT log_text, log_path
                    FROM task_logs
                    WHERE task_id = :task_id
                    ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
                    LIMIT 1
                    """
                ),
                {"task_id": task_id},
            ).mappings().first()
    except Exception as exc:
        log_suppressed_exception("repositories.task.task_log_text", exc, task_id=task_id)
        return None
    if row is None:
        return None
    data = mapping_dict(row)
    if data.get("log_text"):
        return str(data["log_text"])[-tail:]
    log_path = Path(str(data.get("log_path") or ""))
    if str(data.get("log_path") or "") and log_path.is_file():
        return log_path.read_text(encoding="utf-8", errors="replace")[-tail:]
    return ""

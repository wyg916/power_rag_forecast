from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.app.observability import log_suppressed_exception
from backend.app.services.task_runtime import normalize_status, normalize_task_kind, queue_for_kind, task_policy

from .base import dumps_json, jsonable, loads_json, mapping_dict, mapping_list, postgres_engine


ACTIVE_STATUS_SQL = "'pending','queued','running','retrying','cancel_requested'"
TERMINAL_RETRY_STATUSES = {"failed", "timeout", "cancelled"}


def save_task_record(record: dict[str, Any], status: str | None = None, log_text: str | None = None) -> bool:
    engine = postgres_engine()
    if engine is None:
        return False
    kind = str(record.get("task_kind") or record.get("kind") or record.get("task_name") or "")
    policy = task_policy(kind)
    status_value = normalize_status(status or record.get("status") or "pending")
    payload = {
        "task_id": record.get("task_id"),
        "run_id": record.get("run_id"),
        "task_name": record.get("task_name") or kind,
        "task_kind": kind,
        "task_type": record.get("task_type") or kind,
        "status": status_value,
        "payload_json": dumps_json(record.get("payload") or {}),
        "command_json": dumps_json(record.get("command") or []),
        "log_path": record.get("log_path") or "",
        "log_text": log_text,
        "created_at": record.get("created_at"),
        "queued_at": record.get("queued_at"),
        "started_at": record.get("started_at"),
        "ended_at": record.get("ended_at"),
        "finished_at": record.get("finished_at") or record.get("ended_at"),
        "duration_seconds": record.get("duration_seconds"),
        "returncode": record.get("returncode"),
        "error_code": record.get("error_code") or "",
        "error_message": record.get("error_message") or "",
        "error_detail": record.get("error_detail") or "",
        "progress": float(record.get("progress") or 0),
        "message": record.get("message") or "",
        "created_by": record.get("created_by") or "system",
        "retry_count": int(record.get("retry_count") or 0),
        "max_retries": int(record.get("max_retries") if record.get("max_retries") is not None else policy.max_retries),
        "result_ref": record.get("result_ref") or "",
        "metadata_json": dumps_json(record.get("metadata") or record.get("metadata_json") or {}),
        "execution_mode": record.get("execution_mode") or record.get("execution_backend") or "",
        "cancel_requested": bool(record.get("cancel_requested") or False),
        "cancel_reason": record.get("cancel_reason") or "",
        "cancelled_at": record.get("cancelled_at"),
        "timeout_seconds": int(record.get("timeout_seconds") if record.get("timeout_seconds") is not None else policy.timeout_seconds),
        "timeout_at": record.get("timeout_at"),
        "parent_task_id": record.get("parent_task_id") or (record.get("metadata") or {}).get("parent_task_id") or "",
        "original_task_id": record.get("original_task_id") or (record.get("metadata") or {}).get("original_task_id") or "",
        "idempotency_key": record.get("idempotency_key") or "",
        "payload_hash": record.get("payload_hash") or "",
        "dedupe_window_seconds": int(record.get("dedupe_window_seconds") if record.get("dedupe_window_seconds") is not None else policy.dedupe_window_seconds),
        "queue_name": record.get("queue_name") or queue_for_kind(kind),
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
                        queued_at, started_at, ended_at, finished_at, duration_seconds,
                        error_code, error_message, error_detail, progress, message, created_by,
                        retry_count, max_retries, result_ref, metadata_json, execution_mode,
                        cancel_requested, cancel_reason, cancelled_at, timeout_seconds, timeout_at,
                        parent_task_id, original_task_id, idempotency_key, payload_hash,
                        dedupe_window_seconds, queue_name, worker_id, celery_task_id
                    )
                    VALUES (
                        :task_id, :run_id, :task_name, :task_kind, :task_type, :status,
                        CAST(:payload_json AS jsonb), :queued_at, :started_at, :ended_at,
                        :finished_at, :duration_seconds, :error_code, :error_message,
                        :error_detail, :progress, :message, :created_by, :retry_count,
                        :max_retries, :result_ref, CAST(:metadata_json AS jsonb),
                        :execution_mode, :cancel_requested, :cancel_reason, :cancelled_at,
                        :timeout_seconds, :timeout_at, :parent_task_id, :original_task_id,
                        :idempotency_key, :payload_hash, :dedupe_window_seconds, :queue_name,
                        :worker_id, :celery_task_id
                    )
                    ON CONFLICT (task_id) DO UPDATE SET
                        run_id = EXCLUDED.run_id,
                        task_name = EXCLUDED.task_name,
                        task_kind = EXCLUDED.task_kind,
                        task_type = EXCLUDED.task_type,
                        status = EXCLUDED.status,
                        payload_json = EXCLUDED.payload_json,
                        queued_at = COALESCE(task_runs.queued_at, EXCLUDED.queued_at),
                        started_at = COALESCE(task_runs.started_at, EXCLUDED.started_at),
                        ended_at = EXCLUDED.ended_at,
                        finished_at = EXCLUDED.finished_at,
                        duration_seconds = EXCLUDED.duration_seconds,
                        error_code = EXCLUDED.error_code,
                        error_message = EXCLUDED.error_message,
                        error_detail = EXCLUDED.error_detail,
                        progress = EXCLUDED.progress,
                        message = EXCLUDED.message,
                        created_by = COALESCE(task_runs.created_by, EXCLUDED.created_by),
                        retry_count = EXCLUDED.retry_count,
                        max_retries = EXCLUDED.max_retries,
                        result_ref = EXCLUDED.result_ref,
                        metadata_json = EXCLUDED.metadata_json,
                        execution_mode = COALESCE(NULLIF(EXCLUDED.execution_mode, ''), task_runs.execution_mode),
                        cancel_requested = EXCLUDED.cancel_requested,
                        cancel_reason = EXCLUDED.cancel_reason,
                        cancelled_at = COALESCE(EXCLUDED.cancelled_at, task_runs.cancelled_at),
                        timeout_seconds = EXCLUDED.timeout_seconds,
                        timeout_at = COALESCE(EXCLUDED.timeout_at, task_runs.timeout_at),
                        parent_task_id = COALESCE(NULLIF(EXCLUDED.parent_task_id, ''), task_runs.parent_task_id),
                        original_task_id = COALESCE(NULLIF(EXCLUDED.original_task_id, ''), task_runs.original_task_id),
                        idempotency_key = COALESCE(NULLIF(EXCLUDED.idempotency_key, ''), task_runs.idempotency_key),
                        payload_hash = COALESCE(NULLIF(EXCLUDED.payload_hash, ''), task_runs.payload_hash),
                        dedupe_window_seconds = EXCLUDED.dedupe_window_seconds,
                        queue_name = COALESCE(NULLIF(EXCLUDED.queue_name, ''), task_runs.queue_name),
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
                        level = COALESCE(level, 'info'),
                        step = COALESCE(step, 'summary'),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = (
                        SELECT id
                        FROM task_logs
                        WHERE task_id = :task_id
                          AND COALESCE(step, 'summary') = 'summary'
                        ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
                        LIMIT 1
                    )
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
                            , level, step, sequence_no
                        )
                        VALUES (
                            :task_id, :run_id, :task_name, :task_kind, :status,
                            CAST(:command_json AS jsonb), :log_path, :log_text,
                            :started_at, :ended_at, :duration_seconds, :returncode,
                            :error_message, :progress, :message, :result_ref,
                            CAST(:metadata_json AS jsonb), :execution_mode,
                            :cancel_requested, :worker_id, :celery_task_id,
                            'info', 'summary', 0
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
                           created_at, queued_at, started_at, ended_at, finished_at,
                           duration_seconds, error_code, error_message, error_detail,
                           progress, message, created_by, retry_count, max_retries,
                           result_ref, metadata_json, execution_mode, cancel_requested,
                           cancel_reason, cancelled_at, timeout_seconds, timeout_at,
                           parent_task_id, original_task_id, idempotency_key, payload_hash,
                           dedupe_window_seconds, queue_name, worker_id, celery_task_id,
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
                           celery_task_id, updated_at, created_at
                    FROM task_logs
                    WHERE task_id IS NOT NULL
                      AND COALESCE(step, 'summary') = 'summary'
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


def _task_row_to_payload(row: dict[str, Any]) -> dict[str, Any]:
    row["payload"] = loads_json(row.pop("payload_json", None), default={})
    row["metadata"] = loads_json(row.pop("metadata_json", None), default={})
    row.setdefault("kind", row.get("task_kind") or row.get("task_type") or row.get("task_name"))
    row.setdefault("duration_ms", int(float(row.get("duration_seconds") or 0) * 1000))
    row.setdefault("worker_name", row.get("worker_id") or "")
    row.setdefault("handling_suggestion", handling_suggestion_for(row))
    return jsonable(row)


def handling_suggestion_for(record: dict[str, Any]) -> str:
    message = str(record.get("error_message") or record.get("message") or "").lower()
    status = str(record.get("status") or "").lower()
    if "connection" in message or "连接" in message:
        return "检查数据库网络与连接配置"
    if status == "timeout" or "timeout" in message or "超时" in message:
        return "优化数据量或延长超时时间"
    if "memory" in message or "内存" in message:
        return "增加 worker 内存配置"
    if "参数" in message or "param" in message:
        return "检查任务参数后重试"
    if "source" in message or "数据源" in message:
        return "检查数据源接口状态"
    if status in {"failed", "cancelled"}:
        return "查看错误日志后重试"
    return "当前状态无需处理"


def create_pending_task_record(
    *,
    kind: str,
    task_name: str = "",
    payload: dict[str, Any] | None = None,
    queue_name: str = "",
    execution_mode: str = "db_pending",
    created_by: str = "web_user",
    retry_of: str = "",
) -> dict[str, Any]:
    normalized = normalize_task_kind(kind)
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    task_id = f"task_db_{datetime.now().strftime('%Y%m%d%H%M%S')}_{abs(hash((normalized, now))) % 100000:05d}"
    retry_count = int((payload or {}).get("retry_count") or 0)
    record = {
        "task_id": task_id,
        "run_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "kind": normalized,
        "task_name": task_name or normalized,
        "task_type": normalized,
        "status": "pending",
        "payload": payload or {},
        "created_at": now,
        "queued_at": now,
        "progress": 0,
        "message": "task accepted into PostgreSQL queue",
        "created_by": created_by,
        "retry_count": retry_count,
        "max_retries": task_policy(normalized).max_retries,
        "execution_mode": execution_mode,
        "queue_name": queue_name or queue_for_kind(normalized),
        "parent_task_id": retry_of,
        "original_task_id": retry_of,
    }
    save_task_record(record, status="pending", log_text="task accepted into PostgreSQL queue")
    append_task_log(
        task_id,
        level="info",
        step="prepare",
        message="task accepted into PostgreSQL queue",
        status="pending",
        run_id=str(record["run_id"]),
        task_name=str(record["task_name"]),
        task_kind=normalized,
        metadata={"queue_name": record["queue_name"], "retry_of": retry_of},
    )
    return jsonable(record)


def list_task_runs(
    *,
    task_type: str = "",
    kind_keywords: tuple[str, ...] = (),
    status: str = "",
    queue_name: str = "",
    keyword: str = "",
    start_date: str = "",
    end_date: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    engine = postgres_engine()
    safe_page = max(1, int(page or 1))
    safe_size = min(200, max(1, int(page_size or 20)))
    if engine is None:
        return {"list": [], "tasks": [], "total": 0, "page": safe_page, "page_size": safe_size}
    clauses: list[str] = []
    params: dict[str, Any] = {"limit": safe_size, "offset": (safe_page - 1) * safe_size}
    if task_type and task_type != "all":
        clauses.append("(task_kind = :task_type OR task_type = :task_type)")
        params["task_type"] = normalize_task_kind(task_type)
    normalized_keywords = [str(value or "").strip().lower() for value in kind_keywords if str(value or "").strip()]
    if normalized_keywords:
        predicates: list[str] = []
        for index, value in enumerate(normalized_keywords):
            key = f"kind_keyword_{index}"
            predicates.append(
                f"(LOWER(COALESCE(task_kind, '')) LIKE :{key} "
                f"OR LOWER(COALESCE(task_type, '')) LIKE :{key} "
                f"OR LOWER(COALESCE(task_name, '')) LIKE :{key})"
            )
            params[key] = f"%{value}%"
        clauses.append("(" + " OR ".join(predicates) + ")")
    if status and status != "all":
        clauses.append("status = :status")
        params["status"] = normalize_status(status)
    if queue_name and queue_name != "all":
        clauses.append("COALESCE(queue_name, 'default') = :queue_name")
        params["queue_name"] = queue_name
    if keyword:
        clauses.append("(task_id ILIKE :keyword OR task_name ILIKE :keyword OR task_kind ILIKE :keyword)")
        params["keyword"] = f"%{keyword}%"
    if start_date:
        clauses.append("COALESCE(created_at, started_at, queued_at) >= CAST(:start_date AS timestamp)")
        params["start_date"] = start_date
    if end_date:
        clauses.append("COALESCE(created_at, started_at, queued_at) < CAST(:end_date AS timestamp) + INTERVAL '1 day'")
        params["end_date"] = end_date
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    try:
        with engine.connect() as conn:
            total = int(conn.execute(text(f"SELECT COUNT(*) FROM task_runs {where_sql}"), params).scalar() or 0)
            summary = dict(
                conn.execute(
                    text(
                        f"""
                        SELECT
                            MAX(COALESCE(started_at, created_at, queued_at, updated_at)) AS latest_started_at,
                            MAX(CASE WHEN status = 'success'
                                THEN COALESCE(ended_at, finished_at, updated_at) END) AS latest_success_at,
                            COUNT(*) FILTER (
                                WHERE COALESCE(created_at, queued_at, started_at, updated_at) >= CURRENT_DATE
                            ) AS today_task_count
                        FROM task_runs
                        {where_sql}
                        """
                    ),
                    params,
                ).mappings().first()
                or {}
            )
            latest = dict(
                conn.execute(
                    text(
                        f"""
                        SELECT task_id, run_id
                        FROM task_runs
                        {where_sql}
                        ORDER BY COALESCE(created_at, queued_at, started_at, updated_at) DESC, task_id DESC
                        LIMIT 1
                        """
                    ),
                    params,
                ).mappings().first()
                or {}
            )
            rows = conn.execute(
                text(
                    f"""
                    SELECT task_id, run_id, task_name, task_kind, task_kind AS kind,
                           task_type, status, payload_json, created_at, queued_at,
                           started_at, ended_at, finished_at, duration_seconds,
                           error_code, error_message, error_detail, progress, message,
                           created_by, retry_count, max_retries, result_ref, metadata_json,
                           execution_mode, cancel_requested, cancel_reason, cancelled_at,
                           timeout_seconds, timeout_at, parent_task_id, original_task_id,
                           idempotency_key, payload_hash, dedupe_window_seconds,
                           COALESCE(queue_name, 'default') AS queue_name,
                           worker_id, worker_id AS worker_name, celery_task_id, updated_at
                    FROM task_runs
                    {where_sql}
                    ORDER BY COALESCE(created_at, queued_at, started_at, updated_at) DESC, task_id DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            ).mappings().all()
    except Exception as exc:
        log_suppressed_exception("repositories.task.list_task_runs", exc)
        return {"list": [], "tasks": [], "total": 0, "page": safe_page, "page_size": safe_size, "error": str(exc)[:200]}
    items = [_task_row_to_payload(row) for row in mapping_list(rows)]
    return {
        "list": items,
        "tasks": items,
        "total": total,
        "page": safe_page,
        "page_size": safe_size,
        "summary": jsonable(summary),
        "latest": jsonable(latest),
    }


def task_overview() -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {
            "task_total": 0,
            "success_total": 0,
            "running_total": 0,
            "pending_total": 0,
            "failed_total": 0,
            "timeout_total": 0,
            "queue_total": 0,
            "success_rate": 0,
            "day_over_day_change": {},
        }
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*) AS task_total,
                           COUNT(*) FILTER (WHERE status = 'success') AS success_total,
                           COUNT(*) FILTER (WHERE status = 'running') AS running_total,
                           COUNT(*) FILTER (WHERE status IN ('pending','queued','retrying','cancel_requested')) AS pending_total,
                           COUNT(*) FILTER (WHERE status = 'failed') AS failed_total,
                           COUNT(*) FILTER (WHERE status = 'timeout') AS timeout_total,
                           COUNT(DISTINCT COALESCE(queue_name, 'default')) AS queue_total,
                           COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) AS today_total,
                           COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE - INTERVAL '1 day' AND created_at < CURRENT_DATE) AS yesterday_total
                    FROM task_runs
                    """
                )
            ).mappings().first()
    except Exception as exc:
        log_suppressed_exception("repositories.task.task_overview", exc)
        return {"task_total": 0, "success_total": 0, "running_total": 0, "pending_total": 0, "failed_total": 0, "timeout_total": 0, "queue_total": 0, "success_rate": 0, "day_over_day_change": {}, "error": str(exc)[:200]}
    data = mapping_dict(row)
    total = int(data.get("task_total") or 0)
    success = int(data.get("success_total") or 0)
    today = int(data.pop("today_total", 0) or 0)
    yesterday = int(data.pop("yesterday_total", 0) or 0)
    change = 0.0 if yesterday == 0 else round((today - yesterday) * 100 / yesterday, 2)
    data["success_rate"] = round(success * 100 / total, 2) if total else 0
    data["day_over_day_change"] = {"task_total": change}
    return jsonable(data)


def recent_task_logs(*, limit: int = 20, task_id: str = "", queue_name: str = "", level: str = "") -> list[dict[str, Any]]:
    engine = postgres_engine()
    if engine is None:
        return []
    clauses: list[str] = []
    params: dict[str, Any] = {"limit": min(200, max(1, int(limit or 20)))}
    if task_id:
        clauses.append("l.task_id = :task_id")
        params["task_id"] = task_id
    if queue_name and queue_name != "all":
        clauses.append("COALESCE(r.queue_name, 'default') = :queue_name")
        params["queue_name"] = queue_name
    if level and level != "all":
        clauses.append("COALESCE(l.level, 'info') = :level")
        params["level"] = level
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT l.id, l.task_id, l.run_id,
                           COALESCE(l.task_name, r.task_name, r.task_kind) AS task_name,
                           COALESCE(l.task_kind, r.task_kind) AS task_kind,
                           COALESCE(r.queue_name, 'default') AS queue_name,
                           COALESCE(l.worker_id, r.worker_id) AS worker_id,
                           COALESCE(l.celery_task_id, r.celery_task_id) AS celery_task_id,
                           COALESCE(l.level, 'info') AS level,
                           COALESCE(l.step, 'summary') AS step,
                           COALESCE(l.message, l.log_text, l.error_message, '') AS message,
                           l.created_at, l.updated_at
                    FROM task_logs l
                    LEFT JOIN task_runs r ON r.task_id = l.task_id
                    {where_sql}
                    ORDER BY COALESCE(l.created_at, l.updated_at) DESC, l.id DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
    except Exception as exc:
        log_suppressed_exception("repositories.task.recent_task_logs", exc)
        return []
    return jsonable(mapping_list(rows))


def retry_task_candidates(limit: int = 20) -> list[dict[str, Any]]:
    engine = postgres_engine()
    if engine is None:
        return []
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT task_id, run_id, task_name, task_kind, task_kind AS kind,
                           task_type, status, payload_json, created_at, queued_at,
                           started_at, ended_at, finished_at, duration_seconds,
                           error_code, error_message, error_detail, progress, message,
                           created_by, retry_count, max_retries, result_ref, metadata_json,
                           execution_mode, cancel_requested, cancel_reason, cancelled_at,
                           timeout_seconds, timeout_at, parent_task_id, original_task_id,
                           COALESCE(queue_name, 'default') AS queue_name,
                           worker_id, worker_id AS worker_name, celery_task_id, updated_at
                    FROM task_runs
                    WHERE status IN ('failed', 'timeout', 'cancelled')
                      AND COALESCE(retry_count, 0) < COALESCE(max_retries, 0)
                    ORDER BY COALESCE(ended_at, finished_at, updated_at, created_at) DESC
                    LIMIT :limit
                    """
                ),
                {"limit": min(200, max(1, int(limit or 20)))},
            ).mappings().all()
    except Exception as exc:
        log_suppressed_exception("repositories.task.retry_task_candidates", exc)
        return []
    items = []
    for row in mapping_list(rows):
        item = _task_row_to_payload(row)
        item["failed_at"] = item.get("ended_at") or item.get("finished_at") or item.get("updated_at")
        item["reason"] = item.get("error_message") or item.get("message") or item.get("status")
        item["handling_suggestion"] = handling_suggestion_for(item)
        item["action_enabled"] = True
        items.append(item)
    return items


def queue_overview() -> list[dict[str, Any]]:
    engine = postgres_engine()
    if engine is None:
        return []
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT COALESCE(queue_name, 'default') AS queue_name,
                           COUNT(*) AS total,
                           COUNT(*) FILTER (WHERE status = 'success') AS success_count,
                           COUNT(*) FILTER (WHERE status = 'running') AS running_count,
                           COUNT(*) FILTER (WHERE status IN ('pending','queued','retrying','cancel_requested')) AS pending_count,
                           COUNT(*) FILTER (WHERE status = 'failed') AS failed_count,
                           COUNT(*) FILTER (WHERE status = 'timeout') AS timeout_count
                    FROM task_runs
                    GROUP BY COALESCE(queue_name, 'default')
                    ORDER BY total DESC, queue_name
                    """
                )
            ).mappings().all()
    except Exception as exc:
        log_suppressed_exception("repositories.task.queue_overview", exc)
        return []
    data = []
    grand_total = sum(int(row.get("total") or 0) for row in mapping_list(rows)) or 1
    for row in mapping_list(rows):
        total = int(row.get("total") or 0)
        success = int(row.get("success_count") or 0)
        item = dict(row)
        item["success_rate"] = round(success * 100 / total, 2) if total else 0
        item["percent"] = round(total * 100 / grand_total, 2) if grand_total else 0
        item["running"] = item.get("running_count", 0)
        item["pending"] = item.get("pending_count", 0)
        item["failed"] = item.get("failed_count", 0)
        data.append(item)
    return jsonable(data)


def task_trend(days: int = 7) -> list[dict[str, Any]]:
    engine = postgres_engine()
    safe_days = min(90, max(1, int(days or 7)))
    if engine is None:
        return []
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    WITH days AS (
                        SELECT generate_series(
                            CURRENT_DATE - ((:days - 1) * INTERVAL '1 day'),
                            CURRENT_DATE,
                            INTERVAL '1 day'
                        )::date AS day
                    ),
                    stats AS (
                        SELECT COALESCE(created_at, started_at, queued_at)::date AS day,
                               COUNT(*) FILTER (WHERE status = 'success') AS success_count,
                               COUNT(*) FILTER (WHERE status = 'failed') AS failed_count,
                               COUNT(*) FILTER (WHERE status = 'running') AS running_count,
                               COUNT(*) FILTER (WHERE status IN ('pending','queued','retrying','cancel_requested')) AS pending_count,
                               COUNT(*) FILTER (WHERE status = 'timeout') AS timeout_count
                        FROM task_runs
                        WHERE COALESCE(created_at, started_at, queued_at) >= CURRENT_DATE - ((:days - 1) * INTERVAL '1 day')
                        GROUP BY COALESCE(created_at, started_at, queued_at)::date
                    )
                    SELECT days.day AS date,
                           COALESCE(stats.success_count, 0) AS success_count,
                           COALESCE(stats.failed_count, 0) AS failed_count,
                           COALESCE(stats.running_count, 0) AS running_count,
                           COALESCE(stats.pending_count, 0) AS pending_count,
                           COALESCE(stats.timeout_count, 0) AS timeout_count
                    FROM days
                    LEFT JOIN stats ON stats.day = days.day
                    ORDER BY days.day
                    """
                ),
                {"days": safe_days},
            ).mappings().all()
    except Exception as exc:
        log_suppressed_exception("repositories.task.task_trend", exc, days=safe_days)
        return []
    data = []
    for row in mapping_list(rows):
        item = dict(row)
        item["date"] = str(item.get("date") or "")
        item["success"] = item.get("success_count", 0)
        item["failed"] = item.get("failed_count", 0)
        item["running"] = item.get("running_count", 0)
        data.append(item)
    return jsonable(data)


def get_task_record(task_id: str) -> dict[str, Any] | None:
    engine = postgres_engine()
    if engine is not None:
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT task_id, run_id, task_name, task_kind, task_kind AS kind,
                               task_type, status, payload_json, created_at, queued_at,
                               started_at, ended_at, finished_at, duration_seconds,
                               error_code, error_message, error_detail, progress, message,
                               created_by, retry_count, max_retries, result_ref, metadata_json,
                               execution_mode, cancel_requested, cancel_reason, cancelled_at,
                               timeout_seconds, timeout_at, parent_task_id, original_task_id,
                               idempotency_key, payload_hash, dedupe_window_seconds,
                               COALESCE(queue_name, 'default') AS queue_name,
                               worker_id, worker_id AS worker_name, celery_task_id, updated_at
                        FROM task_runs
                        WHERE task_id = :task_id
                        LIMIT 1
                        """
                    ),
                    {"task_id": task_id},
                ).mappings().first()
            if row:
                item = _task_row_to_payload(mapping_dict(row))
                metadata = item.get("metadata") or {}
                item["result_json"] = metadata.get("result") if isinstance(metadata, dict) else None
                item["payload_json"] = item.get("payload") or {}
                item["error_json"] = {
                    "error_code": item.get("error_code") or "",
                    "error_message": item.get("error_message") or "",
                    "error_detail": item.get("error_detail") or "",
                    "handling_suggestion": item.get("handling_suggestion") or handling_suggestion_for(item),
                }
                return item
        except Exception as exc:
            log_suppressed_exception("repositories.task.get_task_record", exc, task_id=task_id)
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
    error_code: str = "",
    error_detail: str = "",
    cancel_requested: bool | None = None,
    cancel_reason: str = "",
    retry_count: int | None = None,
    result_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
    timeout_seconds: int | None = None,
    progress: float | None = None,
    worker_id: str = "",
    celery_task_id: str = "",
    finish: bool = False,
) -> bool:
    current = get_task_record(task_id) or {}
    record = dict(current)
    record["task_id"] = task_id
    record["kind"] = current.get("kind") or current.get("task_kind") or current.get("task_name") or "task"
    record["task_name"] = current.get("task_name") or record["kind"]
    record["status"] = status
    record["message"] = message or current.get("message") or status
    if progress is not None:
        record["progress"] = progress
    record["error_code"] = error_code if error_code else current.get("error_code") or ""
    record["error_message"] = error_message if error_message else current.get("error_message") or ""
    record["error_detail"] = error_detail if error_detail else current.get("error_detail") or ""
    if cancel_requested is not None:
        record["cancel_requested"] = cancel_requested
    if cancel_reason:
        record["cancel_reason"] = cancel_reason
    if retry_count is not None:
        record["retry_count"] = retry_count
    if timeout_seconds is not None:
        record["timeout_seconds"] = timeout_seconds
    if worker_id:
        record["worker_id"] = worker_id
    if celery_task_id:
        record["celery_task_id"] = celery_task_id
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
        if status == "cancelled":
            record["cancelled_at"] = current.get("cancelled_at") or now
        if status == "timeout":
            record["timeout_at"] = current.get("timeout_at") or now
    return save_task_record(record, status=status, log_text=record.get("message") or status)


def append_task_log(
    task_id: str,
    *,
    level: str = "info",
    step: str = "execute",
    message: str = "",
    metadata: dict[str, Any] | None = None,
    status: str = "",
    run_id: str = "",
    task_name: str = "",
    task_kind: str = "",
    sequence_no: int | None = None,
) -> bool:
    engine = postgres_engine()
    if engine is None or not task_id:
        return False
    try:
        with engine.begin() as conn:
            if sequence_no is None:
                sequence_no = int(
                    conn.execute(
                        text("SELECT COALESCE(MAX(sequence_no), 0) + 1 FROM task_logs WHERE task_id = :task_id"),
                        {"task_id": task_id},
                    ).scalar()
                    or 1
                )
            conn.execute(
                text(
                    """
                    INSERT INTO task_logs (
                        task_id, run_id, task_name, task_kind, status, log_text,
                        message, metadata_json, level, step, sequence_no
                    )
                    VALUES (
                        :task_id, :run_id, :task_name, :task_kind, :status, :log_text,
                        :message, CAST(:metadata_json AS jsonb), :level, :step, :sequence_no
                    )
                    """
                ),
                {
                    "task_id": task_id,
                    "run_id": run_id,
                    "task_name": task_name or task_kind,
                    "task_kind": task_kind or task_name,
                    "status": status,
                    "log_text": message,
                    "message": message,
                    "metadata_json": dumps_json(metadata or {}),
                    "level": level,
                    "step": step,
                    "sequence_no": sequence_no,
                },
            )
        return True
    except Exception as exc:
        log_suppressed_exception("repositories.task.append_task_log", exc, task_id=task_id)
        return False


def list_task_log_entries(task_id: str, *, page: int = 1, page_size: int = 50) -> dict[str, Any] | None:
    engine = postgres_engine()
    if engine is None:
        return None
    safe_page = max(1, int(page or 1))
    safe_size = min(200, max(1, int(page_size or 50)))
    offset = (safe_page - 1) * safe_size
    try:
        with engine.connect() as conn:
            total = int(
                conn.execute(text("SELECT COUNT(*) FROM task_logs WHERE task_id = :task_id"), {"task_id": task_id}).scalar()
                or 0
            )
            rows = conn.execute(
                text(
                    """
                    SELECT id, task_id, run_id, task_name, task_kind, status,
                           COALESCE(level, 'info') AS level,
                           COALESCE(step, 'summary') AS step,
                           COALESCE(message, log_text, '') AS message,
                           log_text, metadata_json, sequence_no, created_at, updated_at,
                           error_message
                    FROM task_logs
                    WHERE task_id = :task_id
                    ORDER BY COALESCE(sequence_no, 0), created_at, id
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"task_id": task_id, "limit": safe_size, "offset": offset},
            ).mappings().all()
    except Exception as exc:
        log_suppressed_exception("repositories.task.list_task_log_entries", exc, task_id=task_id)
        return None
    items = []
    for row in mapping_list(rows):
        row["metadata"] = loads_json(row.pop("metadata_json", None), default={})
        items.append(jsonable(row))
    return {
        "task_id": task_id,
        "page": safe_page,
        "page_size": safe_size,
        "total": total,
        "items": items,
        "text": "\n".join(str(item.get("message") or item.get("log_text") or "") for item in items),
    }


def find_active_idempotent_task(kind: str, idempotency_key: str, payload_hash_value: str, dedupe_window_seconds: int) -> dict[str, Any] | None:
    engine = postgres_engine()
    if engine is None or not idempotency_key:
        return None
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT task_id, run_id, task_kind AS kind, status, payload_json,
                           created_at, queued_at, started_at, updated_at,
                           idempotency_key, payload_hash, queue_name, message
                    FROM task_runs
                    WHERE task_kind = :kind
                      AND idempotency_key = :idempotency_key
                      AND payload_hash = :payload_hash
                      AND status IN ('pending','queued','running','retrying','cancel_requested')
                      AND created_at >= CURRENT_TIMESTAMP - (:window_seconds * INTERVAL '1 second')
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "kind": kind,
                    "idempotency_key": idempotency_key,
                    "payload_hash": payload_hash_value,
                    "window_seconds": max(0, int(dedupe_window_seconds or 0)),
                },
            ).mappings().first()
    except Exception as exc:
        log_suppressed_exception("repositories.task.find_active_idempotent_task", exc, kind=kind)
        return None
    if not row:
        return None
    data = mapping_dict(row)
    data["payload"] = loads_json(data.pop("payload_json", None), default={})
    data["deduped"] = True
    data["message"] = "已有相同任务正在运行，已返回已有任务"
    return jsonable(data)


def task_runtime_summary() -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "status_counts": {}, "queue_summary": [], "active_workers": []}
    try:
        with engine.connect() as conn:
            status_rows = conn.execute(
                text("SELECT status, COUNT(*) AS count FROM task_runs GROUP BY status ORDER BY status")
            ).mappings().all()
            queue_rows = conn.execute(
                text(
                    """
                    SELECT COALESCE(queue_name, 'default') AS queue_name,
                           COUNT(*) AS total,
                           COUNT(*) FILTER (WHERE status IN ('pending','queued','retrying')) AS pending,
                           COUNT(*) FILTER (WHERE status = 'running') AS running,
                           COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                           COUNT(*) FILTER (WHERE status = 'timeout') AS timeout
                    FROM task_runs
                    GROUP BY COALESCE(queue_name, 'default')
                    ORDER BY queue_name
                    """
                )
            ).mappings().all()
            worker_rows = conn.execute(
                text(
                    """
                    SELECT DISTINCT worker_id
                    FROM task_runs
                    WHERE COALESCE(worker_id, '') <> ''
                      AND status IN ('running','queued','pending','retrying','cancel_requested')
                    ORDER BY worker_id
                    LIMIT 50
                    """
                )
            ).mappings().all()
    except Exception as exc:
        log_suppressed_exception("repositories.task.task_runtime_summary", exc)
        return {"available": False, "status_counts": {}, "queue_summary": [], "active_workers": [], "error": str(exc)[:200]}
    status_counts = {str(row.get("status") or "unknown"): int(row.get("count") or 0) for row in mapping_list(status_rows)}
    return {
        "available": True,
        "status_counts": status_counts,
        "queue_summary": jsonable(mapping_list(queue_rows)),
        "active_workers": [str(row.get("worker_id")) for row in mapping_list(worker_rows) if row.get("worker_id")],
        "running_task_count": int(status_counts.get("running", 0)),
        "pending_task_count": int(status_counts.get("pending", 0)) + int(status_counts.get("queued", 0)) + int(status_counts.get("retrying", 0)),
        "failed_task_count": int(status_counts.get("failed", 0)),
        "timeout_task_count": int(status_counts.get("timeout", 0)),
    }


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

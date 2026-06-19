from __future__ import annotations

import uuid
import threading
from datetime import datetime
from typing import Any

from backend.app.core.config import get_settings
from backend.app.data_access import jsonable
from backend.app.observability import log_suppressed_exception
from backend.app.repositories.task_repository import append_task_log, find_active_idempotent_task, save_task_record, task_runtime_summary
from backend.app.services.task_runtime import idempotency_key_for, normalize_task_kind, queue_for_kind, task_policy
from backend.app.task_manager import task_manager
from backend.app.workers.task_commands import command_for_kind


SPECIALIZED_TASK_KINDS = {"knowledge_import", "embedding_refresh", "report_generate"}


def task_execution_mode() -> str:
    mode = (get_settings().task_execution_mode or "auto").strip().lower()
    return mode if mode in {"auto", "celery", "local_thread"} else "auto"


def redis_available() -> bool:
    try:
        import redis

        client = redis.Redis.from_url(
            get_settings().redis_url,
            socket_connect_timeout=0.3,
            socket_timeout=0.3,
        )
        return bool(client.ping())
    except Exception as exc:
        log_suppressed_exception("worker.redis_available", exc, redis_url=get_settings().redis_url)
        return False


def celery_available() -> bool:
    try:
        import celery  # noqa: F401
    except Exception as exc:
        log_suppressed_exception("worker.celery_import", exc)
        return False
    return redis_available()


def enqueue_task(kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    kind = normalize_task_kind(kind)
    payload = dict(payload or {})
    mode = task_execution_mode()
    if kind in SPECIALIZED_TASK_KINDS:
        return _enqueue_specialized_task(kind, payload, mode=mode)
    is_celery_available = celery_available()
    if mode == "celery" and not is_celery_available:
        raise RuntimeError("TASK_EXECUTION_MODE=celery requires available Redis/Celery worker.")
    if mode == "local_thread" or (mode == "auto" and not is_celery_available):
        return task_manager.start(kind)

    from backend.app.workers.tasks import run_command_task, sync_core_data_task

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_id = "task_" + uuid.uuid4().hex[:12]
    policy = task_policy(kind)
    dedupe_window = int(payload.get("dedupe_window_seconds") or policy.dedupe_window_seconds)
    idempotency_key, payload_hash = idempotency_key_for(kind, payload)
    if not payload.get("force_new"):
        duplicate = find_active_idempotent_task(kind, idempotency_key, payload_hash, dedupe_window)
        if duplicate:
            return duplicate
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    queue_name = queue_for_kind(kind)
    command = ["celery", "sync_core_data_task"] if kind == "sync_core_data" else command_for_kind(kind)
    record = {
        "task_id": task_id,
        "run_id": run_id,
        "kind": kind,
        "task_name": kind,
        "task_type": kind,
        "status": "pending",
        "payload": payload,
        "command": command,
        "log_path": "",
        "created_at": now,
        "queued_at": now,
        "timeout_seconds": policy.timeout_seconds,
        "max_retries": policy.max_retries,
        "idempotency_key": idempotency_key,
        "payload_hash": payload_hash,
        "dedupe_window_seconds": dedupe_window,
        "queue_name": queue_name,
        "error_message": "",
        "execution_mode": "celery",
    }
    save_task_record(record, status="pending", log_text="task accepted")
    append_task_log(task_id, level="info", step="prepare", message="task accepted", status="pending", run_id=run_id, task_name=kind, task_kind=kind, metadata={"queue_name": queue_name})
    if kind == "sync_core_data":
        async_result = sync_core_data_task.apply_async(args=(task_id, run_id), queue=queue_name)
    else:
        async_result = run_command_task.apply_async(args=(kind, task_id, run_id), queue=queue_name)
    record["celery_task_id"] = async_result.id
    record["execution_backend"] = "celery"
    record["execution_mode"] = "celery"
    save_task_record(record, status="pending", log_text="task submitted to celery")
    append_task_log(task_id, level="info", step="prepare", message="task submitted to celery", status="pending", run_id=run_id, task_name=kind, task_kind=kind, metadata={"celery_task_id": async_result.id, "queue_name": queue_name})
    return jsonable(record)


def _enqueue_specialized_task(kind: str, payload: dict[str, Any], *, mode: str) -> dict[str, Any]:
    kind = normalize_task_kind(kind)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_id = "task_" + uuid.uuid4().hex[:12]
    policy = task_policy(kind)
    dedupe_window = int(payload.get("dedupe_window_seconds") or policy.dedupe_window_seconds)
    idempotency_key, payload_hash = idempotency_key_for(kind, payload)
    if not payload.get("force_new"):
        duplicate = find_active_idempotent_task(kind, idempotency_key, payload_hash, dedupe_window)
        if duplicate:
            return duplicate
    metadata: dict[str, Any] = {}
    if payload.get("retry_of"):
        metadata["parent_task_id"] = payload.get("retry_of")
        metadata["original_task_id"] = payload.get("original_task_id") or payload.get("retry_of")
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    queue_name = queue_for_kind(kind)
    record = {
        "task_id": task_id,
        "run_id": run_id,
        "kind": kind,
        "task_name": kind,
        "task_type": kind,
        "status": "pending",
        "payload": payload,
        "command": [],
        "log_path": "",
        "created_at": now,
        "queued_at": now,
        "progress": 0,
        "message": "pending",
        "error_message": "",
        "retry_count": int(payload.get("retry_count") or 0),
        "max_retries": policy.max_retries,
        "timeout_seconds": policy.timeout_seconds,
        "parent_task_id": metadata.get("parent_task_id") or "",
        "original_task_id": metadata.get("original_task_id") or "",
        "idempotency_key": idempotency_key,
        "payload_hash": payload_hash,
        "dedupe_window_seconds": dedupe_window,
        "queue_name": queue_name,
        "metadata": metadata,
    }
    is_celery_available = celery_available()
    if mode == "celery" and not is_celery_available:
        raise RuntimeError("TASK_EXECUTION_MODE=celery requires available Redis/Celery worker.")
    execution_mode = "celery" if mode == "celery" or (mode == "auto" and is_celery_available) else "local_thread"
    record["execution_mode"] = execution_mode
    save_task_record(record, status="pending", log_text=f"task queued via {execution_mode}")
    append_task_log(task_id, level="info", step="prepare", message=f"task queued via {execution_mode}", status="pending", run_id=run_id, task_name=kind, task_kind=kind, metadata={"queue_name": queue_name})
    if execution_mode == "celery":
        from backend.app.workers.tasks import embedding_refresh_task, knowledge_import_task, report_generate_task

        task_map = {
            "knowledge_import": knowledge_import_task,
            "embedding_refresh": embedding_refresh_task,
            "report_generate": report_generate_task,
        }
        async_result = task_map[kind].apply_async(args=(task_id, run_id, payload), queue=queue_name)
        record["celery_task_id"] = async_result.id
        record["execution_backend"] = "celery"
        record["execution_mode"] = "celery"
        save_task_record(record, status="pending", log_text="task submitted to celery")
        append_task_log(task_id, level="info", step="prepare", message="task submitted to celery", status="pending", run_id=run_id, task_name=kind, task_kind=kind, metadata={"celery_task_id": async_result.id, "queue_name": queue_name})
        return jsonable(record)

    from backend.app.workers.tasks import embedding_refresh_task, knowledge_import_task, report_generate_task

    task_map = {
        "knowledge_import": knowledge_import_task,
        "embedding_refresh": embedding_refresh_task,
        "report_generate": report_generate_task,
    }
    thread = threading.Thread(target=task_map[kind], args=(task_id, run_id, payload), daemon=True)
    thread.start()
    record["execution_backend"] = "local_thread"
    record["execution_mode"] = "local_thread"
    save_task_record(record, status="pending", log_text="task submitted to local_thread")
    append_task_log(task_id, level="info", step="prepare", message="task submitted to local_thread", status="pending", run_id=run_id, task_name=kind, task_kind=kind, metadata={"queue_name": queue_name})
    return jsonable(record)


def task_runtime_health() -> dict[str, Any]:
    mode = task_execution_mode()
    redis_ok = redis_available()
    celery_ok = celery_available()
    summary = task_runtime_summary()
    return {
        "ok": bool(mode != "celery" or celery_ok),
        "execution_mode": mode,
        "redis": {"ok": redis_ok},
        "celery": {"ok": celery_ok},
        "celery_available": celery_ok,
        "active_workers": summary.get("active_workers") or [],
        "queue_summary": summary.get("queue_summary") or [],
        "status_counts": summary.get("status_counts") or {},
        "running_task_count": int(summary.get("running_task_count") or 0),
        "pending_task_count": int(summary.get("pending_task_count") or 0),
        "failed_task_count": int(summary.get("failed_task_count") or 0),
        "timeout_task_count": int(summary.get("timeout_task_count") or 0),
        "message": "ok" if mode != "celery" or celery_ok else "TASK_EXECUTION_MODE=celery but Celery/Redis is unavailable",
    }

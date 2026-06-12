from __future__ import annotations

import uuid
import threading
from datetime import datetime
from typing import Any

from backend.app.core.config import get_settings
from backend.app.data_access import jsonable
from backend.app.observability import log_suppressed_exception
from backend.app.repositories.task_repository import save_task_record
from backend.app.task_manager import task_manager
from backend.app.workers.task_commands import command_for_kind


SPECIALIZED_TASK_KINDS = {"knowledge_import", "embedding_refresh", "report_generate"}


def task_execution_mode() -> str:
    mode = (get_settings().task_execution_mode or "auto").strip().lower()
    return mode if mode in {"auto", "celery", "local_thread"} else "auto"


def _redis_available() -> bool:
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
    return _redis_available()


def enqueue_task(kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    mode = task_execution_mode()
    if kind in SPECIALIZED_TASK_KINDS:
        return _enqueue_specialized_task(kind, payload or {}, mode=mode)
    is_celery_available = celery_available()
    if mode == "celery" and not is_celery_available:
        raise RuntimeError("TASK_EXECUTION_MODE=celery requires available Redis/Celery worker.")
    if mode == "local_thread" or (mode == "auto" and not is_celery_available):
        return task_manager.start(kind)

    from backend.app.workers.tasks import run_command_task, sync_core_data_task

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_id = "task_" + uuid.uuid4().hex[:12]
    command = ["celery", "sync_core_data_task"] if kind == "sync_core_data" else command_for_kind(kind)
    record = {
        "task_id": task_id,
        "run_id": run_id,
        "kind": kind,
        "task_name": kind,
        "status": "pending",
        "payload": payload or {},
        "command": command,
        "log_path": "",
        "started_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "error_message": "",
        "execution_mode": "celery",
    }
    save_task_record(record, status="pending")
    if kind == "sync_core_data":
        async_result = sync_core_data_task.delay(task_id, run_id)
    else:
        async_result = run_command_task.delay(kind, task_id, run_id)
    record["celery_task_id"] = async_result.id
    record["execution_backend"] = "celery"
    record["execution_mode"] = "celery"
    save_task_record(record, status="pending")
    return jsonable(record)


def _enqueue_specialized_task(kind: str, payload: dict[str, Any], *, mode: str) -> dict[str, Any]:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_id = "task_" + uuid.uuid4().hex[:12]
    metadata: dict[str, Any] = {}
    if payload.get("retry_of"):
        metadata["parent_task_id"] = payload.get("retry_of")
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
        "started_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "progress": 0,
        "message": "pending",
        "error_message": "",
        "retry_count": int(payload.get("retry_count") or 0),
        "metadata": metadata,
    }
    is_celery_available = celery_available()
    if mode == "celery" and not is_celery_available:
        raise RuntimeError("TASK_EXECUTION_MODE=celery requires available Redis/Celery worker.")
    execution_mode = "celery" if mode == "celery" or (mode == "auto" and is_celery_available) else "local_thread"
    record["execution_mode"] = execution_mode
    save_task_record(record, status="pending", log_text=f"task queued via {execution_mode}")
    if execution_mode == "celery":
        from backend.app.workers.tasks import embedding_refresh_task, knowledge_import_task, report_generate_task

        task_map = {
            "knowledge_import": knowledge_import_task,
            "embedding_refresh": embedding_refresh_task,
            "report_generate": report_generate_task,
        }
        async_result = task_map[kind].delay(task_id, run_id, payload)
        record["celery_task_id"] = async_result.id
        record["execution_backend"] = "celery"
        record["execution_mode"] = "celery"
        save_task_record(record, status="pending", log_text="task submitted to celery")
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
    return jsonable(record)

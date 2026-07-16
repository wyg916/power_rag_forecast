from __future__ import annotations

import os
import socket
import subprocess
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.config import PROJECT_ROOT, project_paths
from backend.app.observability import log_suppressed_exception
from backend.app.repositories.task_repository import append_task_log, get_task_record, save_task_record, update_task_runtime_state
from backend.app.services.core_data_sync import sync_core_facts_and_tariff_assets
from backend.app.services.rag_health_service import rag_health
from backend.app.services.rag_service import index_local_knowledge
from backend.app.services.task_runtime import queue_for_kind, task_policy, timeout_at
from backend.app.repositories.knowledge_repository import backfill_missing_embeddings, refresh_stale_embeddings
from backend.app.workers.celery_app import celery_app
from backend.app.workers.task_commands import command_for_kind


class TaskExecutionContext:
    def __init__(self, *, task_id: str, run_id: str, kind: str, worker_id: str, celery_task_id: str = "") -> None:
        self.task_id = task_id
        self.run_id = run_id
        self.kind = kind
        self.worker_id = worker_id
        self.celery_task_id = celery_task_id

    def log(self, step: str, message: str, *, level: str = "info", progress: float | None = None, metadata: dict[str, Any] | None = None) -> None:
        if progress is not None:
            update_task_runtime_state(
                self.task_id,
                status="running",
                message=message,
                progress=progress,
                worker_id=self.worker_id,
                celery_task_id=self.celery_task_id,
                metadata={"last_step": step},
            )
        append_task_log(
            self.task_id,
            level=level,
            step=step,
            message=message,
            status="running",
            run_id=self.run_id,
            task_name=self.kind,
            task_kind=self.kind,
            metadata={"worker_id": self.worker_id, "celery_task_id": self.celery_task_id, **(metadata or {})},
        )


def _task_decorator(name: str):
    if celery_app is None:
        return lambda func: func
    return celery_app.task(name=name)


def _creationflags() -> int:
    if os.name != "nt":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def _record(
    *,
    task_id: str,
    run_id: str,
    kind: str,
    status: str,
    command: list[str],
    log_path: str,
    started_at: datetime,
    ended_at: datetime | None = None,
    duration_seconds: float | None = None,
    returncode: int | None = None,
    error_message: str = "",
    progress: float = 0,
    message: str = "",
    result_ref: str = "",
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    execution_mode: str = "",
    worker_id: str = "",
    celery_task_id: str = "",
    cancel_requested: bool = False,
    queued_at: str | datetime | None = None,
    timeout_seconds: int | None = None,
    timeout_at_value: str | datetime | None = None,
    max_retries: int | None = None,
    queue_name: str = "",
    error_code: str = "",
    error_detail: str = "",
    cancel_reason: str = "",
    cancelled_at: str | datetime | None = None,
) -> dict[str, Any]:
    policy = task_policy(kind)
    return {
        "task_id": task_id,
        "run_id": run_id,
        "kind": kind,
        "task_name": kind,
        "status": status,
        "command": command,
        "log_path": log_path,
        "queued_at": queued_at,
        "started_at": started_at,
        "ended_at": ended_at,
        "finished_at": ended_at,
        "duration_seconds": duration_seconds,
        "returncode": returncode,
        "error_code": error_code,
        "error_message": error_message,
        "error_detail": error_detail,
        "progress": progress,
        "message": message,
        "result_ref": result_ref,
        "payload": payload or {},
        "metadata": metadata or {},
        "execution_mode": execution_mode,
        "worker_id": worker_id,
        "celery_task_id": celery_task_id,
        "cancel_requested": cancel_requested,
        "cancel_reason": cancel_reason,
        "cancelled_at": cancelled_at,
        "timeout_seconds": timeout_seconds if timeout_seconds is not None else policy.timeout_seconds,
        "timeout_at": timeout_at_value,
        "max_retries": max_retries if max_retries is not None else policy.max_retries,
        "queue_name": queue_name or queue_for_kind(kind),
    }


def _current_record(task_id: str) -> dict[str, Any]:
    return get_task_record(task_id) or {}


def _cancel_requested(task_id: str) -> bool:
    return bool((_current_record(task_id) or {}).get("cancel_requested"))


def _task_timeout_seconds(kind: str, task_id: str) -> int:
    record = _current_record(task_id)
    return int(record.get("timeout_seconds") or task_policy(kind).timeout_seconds)


@_task_decorator("power_trading.run_command_task")
def run_command_task(kind: str, task_id: str, run_id: str) -> dict[str, Any]:
    started = datetime.now()
    command = command_for_kind(kind)
    policy = task_policy(kind)
    timeout_seconds = _task_timeout_seconds(kind, task_id)
    timeout_at_dt = timeout_at(started, timeout_seconds)
    paths = project_paths()
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    log_path = paths.log_dir / f"celery_task_{kind}_{run_id}.log"
    save_task_record(
        _record(
            task_id=task_id,
            run_id=run_id,
            kind=kind,
            status="running",
            command=command,
            log_path=str(log_path),
            started_at=started,
            progress=10,
            message="running",
            worker_id=socket.gethostname(),
            timeout_seconds=timeout_seconds,
            timeout_at_value=timeout_at_dt,
        ),
        status="running",
    )
    append_task_log(task_id, level="info", step="prepare", message=f"command task started: {kind}", status="running", run_id=run_id, task_name=kind, task_kind=kind, metadata={"command": command, "timeout_seconds": timeout_seconds})
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["NO_PAUSE"] = "1"
    start_counter = time.perf_counter()
    with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
        log_file.write(f"[{started.isoformat(sep=' ', timespec='seconds')}] Celery task started: {kind}\n")
        log_file.write("command: " + " ".join(command) + "\n")
        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            stdin=subprocess.DEVNULL,
            creationflags=_creationflags(),
        )
        status = "running"
        error_message = ""
        error_code = ""
        while True:
            returncode = process.poll()
            if returncode is not None:
                status = "success" if returncode == 0 else "failed"
                error_message = "" if returncode == 0 else f"returncode={returncode}"
                error_code = "" if returncode == 0 else "PROCESS_FAILED"
                break
            if _cancel_requested(task_id):
                process.terminate()
                try:
                    process.wait(timeout=10)
                except Exception:
                    process.kill()
                    process.wait(timeout=10)
                returncode = process.returncode
                status = "cancelled"
                error_message = "cancel requested"
                error_code = "TASK_CANCELLED"
                append_task_log(task_id, level="warning", step="cleanup", message="task cancelled by request", status=status, run_id=run_id, task_name=kind, task_kind=kind)
                break
            if time.perf_counter() - start_counter > timeout_seconds:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except Exception:
                    process.kill()
                    process.wait(timeout=10)
                returncode = process.returncode
                status = "timeout"
                error_message = f"task timeout after {timeout_seconds}s"
                error_code = "TASK_TIMEOUT"
                append_task_log(task_id, level="error", step="execute", message=error_message, status=status, run_id=run_id, task_name=kind, task_kind=kind)
                break
            time.sleep(2)
        ended = datetime.now()
        log_file.write(f"\n[{ended.isoformat(sep=' ', timespec='seconds')}] Celery task finished: {status}, returncode={returncode}\n")
    duration = round(time.perf_counter() - start_counter, 3)
    log_text = Path(log_path).read_text(encoding="utf-8", errors="replace")[-4000:]
    final_record = _record(
        task_id=task_id,
        run_id=run_id,
        kind=kind,
        status=status,
        command=command,
        log_path=str(log_path),
        started_at=started,
        ended_at=ended,
        duration_seconds=duration,
        returncode=returncode,
        error_code=error_code,
        error_message=error_message,
        error_detail=log_text[-1200:] if status in {"failed", "timeout"} else "",
        progress=100,
        message=status,
        result_ref=str(log_path),
        worker_id=socket.gethostname(),
        timeout_seconds=timeout_seconds,
        timeout_at_value=timeout_at_dt,
        max_retries=policy.max_retries,
        cancel_reason="cancel requested" if status == "cancelled" else "",
        cancelled_at=ended if status == "cancelled" else None,
    )
    save_task_record(final_record, status=status, log_text=log_text)
    append_task_log(task_id, level="error" if status in {"failed", "timeout"} else "info", step="persist", message=f"task finished: {status}", status=status, run_id=run_id, task_name=kind, task_kind=kind, metadata={"duration_seconds": duration, "result_ref": str(log_path)})
    return final_record


def _run_python_task(
    *,
    task_id: str,
    run_id: str,
    kind: str,
    payload: dict[str, Any] | None,
    handler,
) -> dict[str, Any]:
    started = datetime.now()
    worker_id = socket.gethostname()
    celery_task_id = ""
    try:
        from celery import current_task

        celery_task_id = str(getattr(getattr(current_task, "request", None), "id", "") or "")
    except Exception:
        celery_task_id = ""
    policy = task_policy(kind)
    timeout_seconds = _task_timeout_seconds(kind, task_id)
    timeout_at_dt = timeout_at(started, timeout_seconds)
    log_lines = [f"[{started.isoformat(sep=' ', timespec='seconds')}] Task started: {kind}"]
    save_task_record(
        _record(
            task_id=task_id,
            run_id=run_id,
            kind=kind,
            status="running",
            command=[],
            log_path="",
            started_at=started,
            progress=10,
            message="running",
            payload=payload,
            worker_id=worker_id,
            celery_task_id=celery_task_id,
            timeout_seconds=timeout_seconds,
            timeout_at_value=timeout_at_dt,
            max_retries=policy.max_retries,
        ),
        status="running",
        log_text="\n".join(log_lines),
    )
    append_task_log(task_id, level="info", step="prepare", message=f"python task started: {kind}", status="running", run_id=run_id, task_name=kind, task_kind=kind, metadata={"timeout_seconds": timeout_seconds})
    started_counter = time.perf_counter()
    context = TaskExecutionContext(task_id=task_id, run_id=run_id, kind=kind, worker_id=worker_id, celery_task_id=celery_task_id)
    try:
        if _cancel_requested(task_id):
            ended = datetime.now()
            final_record = _record(
                task_id=task_id,
                run_id=run_id,
                kind=kind,
                status="cancelled",
                command=[],
                log_path="",
                started_at=started,
                ended_at=ended,
                duration_seconds=round(time.perf_counter() - started_counter, 3),
                returncode=1,
                error_code="TASK_CANCELLED",
                error_message="cancel requested before execution",
                progress=100,
                message="cancelled",
                payload=payload,
                worker_id=worker_id,
                celery_task_id=celery_task_id,
                timeout_seconds=timeout_seconds,
                timeout_at_value=timeout_at_dt,
                cancel_reason="cancel requested before execution",
                cancelled_at=ended,
            )
            save_task_record(final_record, status="cancelled", log_text="cancel requested before execution")
            append_task_log(task_id, level="warning", step="validate", message="cancel requested before execution", status="cancelled", run_id=run_id, task_name=kind, task_kind=kind)
            return final_record
        context.log("execute", "handler execution started", progress=15, metadata={"timeout_seconds": timeout_seconds})
        try:
            import inspect

            accepts_context = len(inspect.signature(handler).parameters) >= 2
        except Exception:
            accepts_context = False
        result = handler(payload or {}, context) if accepts_context else handler(payload or {})
        ended = datetime.now()
        duration = round(time.perf_counter() - started_counter, 3)
        if _cancel_requested(task_id):
            status = "cancelled"
            error_code = "TASK_CANCELLED"
            error_message = "cancel requested"
            message = "cancelled"
            cancel_reason = "cancel requested"
        elif duration > timeout_seconds:
            status = "timeout"
            error_code = "TASK_TIMEOUT"
            error_message = f"task timeout after {timeout_seconds}s"
            message = "timeout"
            cancel_reason = ""
        else:
            status = "success"
            error_code = ""
            error_message = ""
            message = "success"
            cancel_reason = ""
        final_record = _record(
            task_id=task_id,
            run_id=run_id,
            kind=kind,
            status=status,
            command=[],
            log_path="",
            started_at=started,
            ended_at=ended,
            duration_seconds=duration,
            returncode=0 if status == "success" else 1,
            error_code=error_code,
            error_message=error_message,
            progress=100,
            message=message,
            result_ref=str(result.get("result_ref") or result.get("report_path") or result.get("stats") or kind),
            payload=payload,
            metadata={"result": result},
            worker_id=worker_id,
            celery_task_id=celery_task_id,
            timeout_seconds=timeout_seconds,
            timeout_at_value=timeout_at_dt,
            max_retries=policy.max_retries,
            cancel_reason=cancel_reason,
            cancelled_at=ended if status == "cancelled" else None,
        )
        log_lines.append(json_safe(result))
        save_task_record(final_record, status=status, log_text="\n".join(log_lines)[-4000:])
        append_task_log(task_id, level="error" if status == "timeout" else "info", step="persist", message=f"task finished: {status}", status=status, run_id=run_id, task_name=kind, task_kind=kind, metadata={"duration_seconds": duration, "result_ref": final_record.get("result_ref"), "worker_id": worker_id})
        return final_record
    except Exception as exc:
        ended = datetime.now()
        error = str(exc)
        error_detail = traceback.format_exc()[-4000:]
        log_suppressed_exception(f"celery.{kind}", exc, task_id=task_id, run_id=run_id)
        final_record = _record(
            task_id=task_id,
            run_id=run_id,
            kind=kind,
            status="failed",
            command=[],
            log_path="",
            started_at=started,
            ended_at=ended,
            duration_seconds=round(time.perf_counter() - started_counter, 3),
            returncode=1,
            error_code=exc.__class__.__name__,
            error_message=error,
            error_detail=error_detail,
            progress=100,
            message="failed",
            payload=payload,
            worker_id=worker_id,
            celery_task_id=celery_task_id,
            timeout_seconds=timeout_seconds,
            timeout_at_value=timeout_at_dt,
            max_retries=policy.max_retries,
        )
        log_lines.append(error)
        save_task_record(final_record, status="failed", log_text="\n".join(log_lines)[-4000:])
        append_task_log(task_id, level="error", step="execute", message=error, status="failed", run_id=run_id, task_name=kind, task_kind=kind, metadata={"error_code": exc.__class__.__name__, "error_detail": error_detail, "worker_id": worker_id})
        return final_record


def json_safe(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str)


def _knowledge_import_handler(payload: dict[str, Any], context: TaskExecutionContext | None = None) -> dict[str, Any]:
    limit_files = int(payload.get("limit_files") or 300)
    if context:
        context.log("index", "开始知识库本地索引", progress=35, metadata={"limit_files": limit_files})
    result = index_local_knowledge(limit_files=limit_files)
    result["result_ref"] = "kb_documents/kb_chunks"
    return result


def _embedding_refresh_handler(payload: dict[str, Any], context: TaskExecutionContext | None = None) -> dict[str, Any]:
    if context:
        context.log("health", "检查 RAG 健康状态", progress=28)
    before_health = rag_health()
    if context:
        context.log("embedding", "补齐缺失向量", progress=48)
    backfill = backfill_missing_embeddings()
    if context:
        context.log("embedding", "刷新过期向量", progress=68)
    refresh = refresh_stale_embeddings()
    after_health = rag_health()
    warnings: list[str] = []
    if before_health.get("fallback_enabled"):
        warnings.append("RAG fallback was enabled before embedding refresh: " + ", ".join(before_health.get("fallback_reasons") or []))
    if after_health.get("fallback_enabled"):
        warnings.append("RAG fallback is enabled after embedding refresh: " + ", ".join(after_health.get("fallback_reasons") or []))
    result = {
        "embedding_backfill": backfill,
        "embedding_refresh": refresh,
        "rag_health_before": before_health,
        "rag_health_after": after_health,
        "warnings": warnings,
        "result_ref": "kb_chunks.embedding_json",
    }
    return result


@_task_decorator("power_trading.knowledge_import_task")
def knowledge_import_task(task_id: str, run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return _run_python_task(task_id=task_id, run_id=run_id, kind="knowledge_import", payload=payload, handler=_knowledge_import_handler)


@_task_decorator("power_trading.embedding_refresh_task")
def embedding_refresh_task(task_id: str, run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return _run_python_task(task_id=task_id, run_id=run_id, kind="embedding_refresh", payload=payload, handler=_embedding_refresh_handler)


@_task_decorator("power_trading.report_generate_task")
def report_generate_task(task_id: str, run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    result = run_command_task("report_only", task_id, run_id)
    result["kind"] = "report_generate"
    result["task_name"] = "report_generate"
    result["task_type"] = "report_generate"
    result["payload"] = payload or {}
    if not result.get("result_ref"):
        result["result_ref"] = str(result.get("log_path") or "report_generate")
    save_task_record(result, status=str(result.get("status") or "success"))
    return result


@_task_decorator("power_trading.run_price_predict_task")
def run_price_predict_task(task_id: str, run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend.app.services.task_business_handlers import run_price_predict

    return _run_python_task(task_id=task_id, run_id=run_id, kind="price_predict", payload=payload, handler=run_price_predict)


@_task_decorator("power_trading.run_data_sync_task")
def run_data_sync_task(task_id: str, run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend.app.services.task_business_handlers import run_data_sync

    return _run_python_task(task_id=task_id, run_id=run_id, kind="data_sync", payload=payload, handler=run_data_sync)


@_task_decorator("power_trading.run_report_daily_task")
def run_report_daily_task(task_id: str, run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend.app.services.task_business_handlers import run_report_daily

    return _run_python_task(task_id=task_id, run_id=run_id, kind="report_daily", payload=payload, handler=run_report_daily)


@_task_decorator("power_trading.health_check_task")
def health_check_task() -> dict[str, Any]:
    return {"status": "ok", "worker_id": socket.gethostname(), "checked_at": datetime.now().isoformat(sep=" ", timespec="seconds")}


@_task_decorator("power_trading.sync_core_data_task")
def sync_core_data_task(task_id: str, run_id: str) -> dict[str, Any]:
    started = datetime.now()
    log_lines: list[str] = []
    command = ["python", "-X", "utf8", "13_sync_core_data_to_db.py"]
    save_task_record(
        _record(
            task_id=task_id,
            run_id=run_id,
            kind="sync_core_data",
            status="running",
            command=command,
            log_path="",
            started_at=started,
            progress=10,
            message="running",
            worker_id=socket.gethostname(),
            timeout_seconds=_task_timeout_seconds("sync_core_data", task_id),
            timeout_at_value=timeout_at(started, _task_timeout_seconds("sync_core_data", task_id)),
        ),
        status="running",
    )
    append_task_log(task_id, level="info", step="prepare", message="sync core data task started", status="running", run_id=run_id, task_name="sync_core_data", task_kind="sync_core_data")

    def log(message: str) -> None:
        log_lines.append(f"[{datetime.now().isoformat(sep=' ', timespec='seconds')}] {message}")

    start_counter = time.perf_counter()
    try:
        if _cancel_requested(task_id):
            raise RuntimeError("cancel requested before sync")
        result = sync_core_facts_and_tariff_assets(log=log)
        status = "success" if result.get("available") else "failed"
        error = "" if status == "success" else str(result)
        returncode = 0 if status == "success" else 1
    except Exception as exc:
        log_suppressed_exception("celery.sync_core_data_task", exc, task_id=task_id, run_id=run_id)
        result = {"available": False, "message": str(exc)}
        status = "failed"
        error = str(exc)
        returncode = 1
    ended = datetime.now()
    duration = round(time.perf_counter() - start_counter, 3)
    timeout_seconds = _task_timeout_seconds("sync_core_data", task_id)
    if status == "success" and duration > timeout_seconds:
        status = "timeout"
        error = f"task timeout after {timeout_seconds}s"
        returncode = 1
    final_record = _record(
        task_id=task_id,
        run_id=run_id,
        kind="sync_core_data",
        status=status,
        command=command,
        log_path="",
        started_at=started,
        ended_at=ended,
        duration_seconds=duration,
        returncode=returncode,
        error_code="TASK_TIMEOUT" if status == "timeout" else ("SYNC_FAILED" if status == "failed" else ""),
        error_message=error,
        progress=100,
        message=status,
        result_ref="core_data_sync" if status == "success" else "",
        worker_id=socket.gethostname(),
        timeout_seconds=timeout_seconds,
        timeout_at_value=timeout_at(started, timeout_seconds),
    )
    log_lines.append(str(result))
    save_task_record(final_record, status=status, log_text="\n".join(log_lines)[-4000:])
    append_task_log(task_id, level="error" if status in {"failed", "timeout"} else "info", step="persist", message=f"sync core data finished: {status}", status=status, run_id=run_id, task_name="sync_core_data", task_kind="sync_core_data", metadata={"duration_seconds": duration})
    return final_record

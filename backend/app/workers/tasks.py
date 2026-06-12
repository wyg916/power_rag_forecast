from __future__ import annotations

import os
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.config import PROJECT_ROOT, project_paths
from backend.app.observability import log_suppressed_exception
from backend.app.repositories.task_repository import save_task_record
from backend.app.services.core_data_sync import sync_core_facts_and_tariff_assets
from backend.app.services.rag_service import index_local_knowledge
from backend.app.repositories.knowledge_repository import backfill_missing_embeddings, refresh_stale_embeddings
from backend.app.workers.celery_app import celery_app
from backend.app.workers.task_commands import command_for_kind


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
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "run_id": run_id,
        "kind": kind,
        "task_name": kind,
        "status": status,
        "command": command,
        "log_path": log_path,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": duration_seconds,
        "returncode": returncode,
        "error_message": error_message,
        "progress": progress,
        "message": message,
        "result_ref": result_ref,
        "payload": payload or {},
        "metadata": metadata or {},
        "execution_mode": execution_mode,
        "worker_id": worker_id,
        "celery_task_id": celery_task_id,
        "cancel_requested": cancel_requested,
    }


@_task_decorator("power_trading.run_command_task")
def run_command_task(kind: str, task_id: str, run_id: str) -> dict[str, Any]:
    started = datetime.now()
    command = command_for_kind(kind)
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
        ),
        status="running",
    )
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["NO_PAUSE"] = "1"
    start_counter = time.perf_counter()
    with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
        log_file.write(f"[{started.isoformat(sep=' ', timespec='seconds')}] Celery task started: {kind}\n")
        log_file.write("command: " + " ".join(command) + "\n")
        process = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
            creationflags=_creationflags(),
        )
        ended = datetime.now()
        status = "success" if process.returncode == 0 else "failed"
        log_file.write(f"\n[{ended.isoformat(sep=' ', timespec='seconds')}] Celery task finished: {status}, returncode={process.returncode}\n")
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
        returncode=process.returncode,
        error_message="" if process.returncode == 0 else f"returncode={process.returncode}",
        progress=100 if process.returncode == 0 else 100,
        message="success" if process.returncode == 0 else "failed",
        result_ref=str(log_path),
        worker_id=socket.gethostname(),
    )
    save_task_record(final_record, status=status, log_text=log_text)
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
            worker_id=socket.gethostname(),
        ),
        status="running",
        log_text="\n".join(log_lines),
    )
    started_counter = time.perf_counter()
    try:
        result = handler(payload or {})
        ended = datetime.now()
        final_record = _record(
            task_id=task_id,
            run_id=run_id,
            kind=kind,
            status="success",
            command=[],
            log_path="",
            started_at=started,
            ended_at=ended,
            duration_seconds=round(time.perf_counter() - started_counter, 3),
            returncode=0,
            progress=100,
            message="success",
            result_ref=str(result.get("result_ref") or result.get("report_path") or result.get("stats") or kind),
            payload=payload,
            metadata={"result": result},
            worker_id=socket.gethostname(),
        )
        log_lines.append(json_safe(result))
        save_task_record(final_record, status="success", log_text="\n".join(log_lines)[-4000:])
        return final_record
    except Exception as exc:
        ended = datetime.now()
        error = str(exc)
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
            error_message=error,
            progress=100,
            message="failed",
            payload=payload,
            worker_id=socket.gethostname(),
        )
        log_lines.append(error)
        save_task_record(final_record, status="failed", log_text="\n".join(log_lines)[-4000:])
        return final_record


def json_safe(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str)


def _knowledge_import_handler(payload: dict[str, Any]) -> dict[str, Any]:
    limit_files = int(payload.get("limit_files") or 300)
    result = index_local_knowledge(limit_files=limit_files)
    result["result_ref"] = "kb_documents/kb_chunks"
    return result


def _embedding_refresh_handler(payload: dict[str, Any]) -> dict[str, Any]:
    result = {
        "embedding_backfill": backfill_missing_embeddings(),
        "embedding_refresh": refresh_stale_embeddings(),
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
        ),
        status="running",
    )

    def log(message: str) -> None:
        log_lines.append(f"[{datetime.now().isoformat(sep=' ', timespec='seconds')}] {message}")

    start_counter = time.perf_counter()
    try:
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
    final_record = _record(
        task_id=task_id,
        run_id=run_id,
        kind="sync_core_data",
        status=status,
        command=command,
        log_path="",
        started_at=started,
        ended_at=ended,
        duration_seconds=round(time.perf_counter() - start_counter, 3),
        returncode=returncode,
        error_message=error,
        progress=100,
        message=status,
        result_ref="core_data_sync" if status == "success" else "",
        worker_id=socket.gethostname(),
    )
    log_lines.append(str(result))
    save_task_record(final_record, status=status, log_text="\n".join(log_lines)[-4000:])
    return final_record

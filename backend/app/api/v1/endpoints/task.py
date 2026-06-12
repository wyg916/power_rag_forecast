from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

from ....core.security import CurrentUser, require_permission
from ....repositories.audit_repository import write_audit_log
from ....schedule_service import create_scheduled_task, delete_scheduled_task, list_scheduled_tasks
from ....schemas import ScheduledTaskCreateRequest, TaskCreateRequest, TaskRunRequest
from ....repositories.task_repository import get_task_record, list_recent_tasks, save_task_record, task_log_text, update_task_runtime_state
from ....task_manager import task_manager
from ....workers.dispatcher import celery_available, enqueue_task, task_execution_mode


router = APIRouter()


def _enqueue_or_503(kind: str, payload: dict | None = None) -> dict:
    try:
        return enqueue_task(kind, payload or {})
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/api/tasks/run")
def task_run(
    payload: TaskRunRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("task:run"))],
) -> dict:
    result = _enqueue_or_503(payload.kind, payload.payload or {})
    write_audit_log(
        action="task.run",
        user=user,
        resource_type="task",
        resource_id=str(result.get("task_id") or payload.kind),
        ip_address=request.client.host if request.client else "",
        metadata={"kind": payload.kind, "task": result},
    )
    return result


@router.post("/api/tasks")
def task_create(
    payload: TaskCreateRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("task:run"))],
) -> dict:
    create_payload = dict(payload.payload or {})
    create_payload.setdefault("created_by", payload.created_by)
    result = _enqueue_or_503(payload.kind, create_payload)
    write_audit_log(
        action="task.create",
        user=user,
        resource_type="task",
        resource_id=str(result.get("task_id") or payload.kind),
        ip_address=request.client.host if request.client else "",
        metadata={"kind": payload.kind, "task": result},
    )
    return result


@router.get("/api/tasks")
def task_list() -> dict:
    memory_rows = task_manager.list()
    merged = {row.get("task_id"): row for row in list_recent_tasks(limit=100)}
    for row in memory_rows:
        merged[row.get("task_id")] = row
    rows = [row for row in merged.values() if row.get("task_id")]
    rows.sort(key=lambda item: str(item.get("started_at") or item.get("updated_at") or ""), reverse=True)
    return {"tasks": rows[:100]}


@router.get("/api/tasks/health")
def task_health() -> dict:
    mode = task_execution_mode()
    celery_ok = celery_available()
    return {
        "ok": bool(mode != "celery" or celery_ok),
        "execution_mode": mode,
        "celery_available": celery_ok,
        "message": "ok" if mode != "celery" or celery_ok else "TASK_EXECUTION_MODE=celery but Celery/Redis is unavailable",
    }


@router.get("/api/tasks/{task_id}")
def task_detail(task_id: str) -> dict:
    try:
        return task_manager.get(task_id)
    except KeyError:
        record = get_task_record(task_id)
        if record:
            return record
        raise HTTPException(status_code=404, detail="任务不存在") from None


@router.get("/api/tasks/{task_id}/logs", response_class=PlainTextResponse)
def task_logs(task_id: str) -> str:
    try:
        return task_manager.logs(task_id)
    except KeyError:
        value = task_log_text(task_id)
        if value is not None:
            return value
        raise HTTPException(status_code=404, detail="任务不存在") from None


@router.post("/api/tasks/{task_id}/cancel")
def task_cancel(
    task_id: str,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("task:run"))],
) -> dict:
    record = get_task_record(task_id)
    if record:
        status = str(record.get("status") or "").lower()
        if status in {"success", "failed", "cancelled"}:
            result = {"task_id": task_id, "status": status, "message": "task already finished"}
        elif status in {"pending", "queued"}:
            update_task_runtime_state(task_id, status="cancelled", message="cancelled before start", cancel_requested=True, finish=True)
            result = {"task_id": task_id, "status": "cancelled", "message": "pending task cancelled"}
        else:
            revoke_message = "cancel request recorded"
            celery_task_id = str(record.get("celery_task_id") or "")
            if celery_task_id:
                try:
                    from ....workers.celery_app import celery_app

                    if celery_app is not None:
                        celery_app.control.revoke(celery_task_id, terminate=True)
                        revoke_message = "cancel request recorded and celery revoke attempted"
                except Exception:
                    revoke_message = "cancel request recorded; celery revoke failed"
            update_task_runtime_state(
                task_id,
                status="cancel_requested",
                message=revoke_message,
                cancel_requested=True,
                metadata={"cancel_requested_by": getattr(user, "username", "system")},
            )
            result = {"task_id": task_id, "status": "cancel_requested", "message": revoke_message}
        write_audit_log(
            action="task.cancel",
            user=user,
            resource_type="task",
            resource_id=task_id,
            ip_address=request.client.host if request.client else "",
            metadata=result,
        )
        return result
    try:
        result = task_manager.cancel(task_id)
        write_audit_log(
            action="task.cancel",
            user=user,
            resource_type="task",
            resource_id=task_id,
            ip_address=request.client.host if request.client else "",
            metadata=result,
        )
        return result
    except KeyError:
        raise HTTPException(status_code=404, detail="任务不存在") from None


@router.post("/api/tasks/{task_id}/retry")
def task_retry(
    task_id: str,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("task:run"))],
) -> dict:
    record = get_task_record(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="task not found")
    status = str(record.get("status") or "").lower()
    if status in {"running", "pending", "queued", "cancel_requested"}:
        raise HTTPException(status_code=400, detail=f"task status {status} cannot be retried")
    if status not in {"failed", "cancelled"}:
        raise HTTPException(status_code=400, detail=f"task status {status or 'unknown'} cannot be retried")
    payload = dict(record.get("payload") or {})
    payload["retry_of"] = task_id
    payload["retry_count"] = int(record.get("retry_count") or 0) + 1
    result = _enqueue_or_503(str(record.get("kind") or record.get("task_kind") or record.get("task_name")), payload)
    write_audit_log(
        action="task.retry",
        user=user,
        resource_type="task",
        resource_id=task_id,
        ip_address=request.client.host if request.client else "",
        metadata={"retry_task": result},
    )
    return result


@router.get("/api/scheduled-tasks")
def scheduled_tasks() -> dict:
    return list_scheduled_tasks()


@router.post("/api/scheduled-tasks")
def scheduled_task_create(
    payload: ScheduledTaskCreateRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("task:run"))],
) -> dict:
    try:
        result = create_scheduled_task(payload.name, payload.mode, payload.run_time, payload.highest)
        write_audit_log(
            action="task.schedule_create",
            user=user,
            resource_type="scheduled_task",
            resource_id=payload.name,
            ip_address=request.client.host if request.client else "",
            metadata={"payload": payload.dict(), "result": result},
        )
        return result
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/scheduled-tasks/{task_name}")
def scheduled_task_delete(
    task_name: str,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("task:run"))],
) -> dict:
    try:
        result = delete_scheduled_task(task_name)
        write_audit_log(
            action="task.schedule_delete",
            user=user,
            resource_type="scheduled_task",
            resource_id=task_name,
            ip_address=request.client.host if request.client else "",
            metadata=result,
        )
        return result
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

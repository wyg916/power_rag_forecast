from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ....core.security import CurrentUser, require_permission
from ....repositories.audit_repository import write_audit_log
from ....repositories.task_repository import (
    append_task_log,
    create_pending_task_record,
    get_task_record,
    list_recent_tasks,
    list_task_log_entries,
    list_task_runs,
    queue_overview,
    recent_task_logs,
    retry_task_candidates,
    task_log_text,
    task_overview,
    task_trend,
    update_task_runtime_state,
)
from ....schedule_service import create_scheduled_task, delete_scheduled_task, list_scheduled_tasks
from ....schemas import ScheduledTaskCreateRequest, TaskCreateRequest, TaskRunRequest
from ....services.dashboard_home_service import task_recent_payload
from ....services.task_runtime import normalize_task_kind, task_policy
from ....task_manager import task_manager
from ....workers.dispatcher import BUSINESS_TASK_KINDS, enqueue_task, task_runtime_health
from ....workers.task_commands import command_for_kind


router = APIRouter()


def _enqueue_or_503(kind: str, payload: dict | None = None) -> dict:
    try:
        return enqueue_task(kind, payload or {})
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _runtime_payload(payload: TaskRunRequest) -> dict:
    data = dict(payload.payload or {})
    if payload.idempotency_key:
        data["idempotency_key"] = payload.idempotency_key
    if payload.dedupe_window_seconds is not None:
        data["dedupe_window_seconds"] = payload.dedupe_window_seconds
    return data


@router.post("/api/tasks/run")
def task_run(
    payload: TaskRunRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("task:run"))],
) -> dict:
    result = _enqueue_or_503(payload.kind, _runtime_payload(payload))
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
    create_payload = _runtime_payload(payload)
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


@router.get("/api/tasks/overview")
def task_center_overview() -> dict:
    return task_overview()


@router.get("/api/tasks/runs")
def task_runs(
    task_type: str = Query(default=""),
    status: str = Query(default=""),
    queue_name: str = Query(default=""),
    keyword: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> dict:
    return list_task_runs(
        task_type=task_type,
        status=status,
        queue_name=queue_name,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )


@router.get("/api/tasks")
def task_list(
    task_type: str = Query(default=""),
    status: str = Query(default=""),
    queue_name: str = Query(default=""),
    keyword: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
) -> dict:
    if any([task_type, status, queue_name, keyword, start_date, end_date]) or page != 1 or page_size != 100:
        return list_task_runs(
            task_type=task_type,
            status=status,
            queue_name=queue_name,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )
    memory_rows = task_manager.list()
    merged = {row.get("task_id"): row for row in list_recent_tasks(limit=100)}
    for row in memory_rows:
        merged[row.get("task_id")] = row
    rows = [row for row in merged.values() if row.get("task_id")]
    rows.sort(key=lambda item: str(item.get("started_at") or item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return {"tasks": rows[:100]}


@router.get("/api/tasks/health")
def task_health() -> dict:
    return task_runtime_health()


@router.get("/api/tasks/logs/recent")
def task_logs_recent(
    limit: int = Query(default=20, ge=1, le=200),
    task_id: str = Query(default=""),
    queue_name: str = Query(default=""),
    level: str = Query(default=""),
) -> dict:
    return {"items": recent_task_logs(limit=limit, task_id=task_id, queue_name=queue_name, level=level)}


@router.get("/api/tasks/retry/recent")
def task_retry_recent(limit: int = Query(default=20, ge=1, le=200)) -> dict:
    return {"items": retry_task_candidates(limit=limit)}


@router.get("/api/tasks/queues/overview")
def task_queues_overview() -> dict:
    return {"items": queue_overview()}


@router.get("/api/tasks/trend")
def task_trend_api(days: int = Query(default=7, ge=1, le=90)) -> dict:
    return {"items": task_trend(days=days)}


@router.post("/api/tasks/start")
def task_start(
    payload: dict,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("task:run"))],
) -> dict:
    kind = normalize_task_kind(str(payload.get("task_type") or payload.get("task_kind") or payload.get("kind") or "health_check"))
    task_payload = dict(payload.get("payload") or {})
    task_payload.setdefault("created_by", getattr(user, "username", "web_user"))
    dispatch_error = ""
    can_dispatch = kind in {"knowledge_import", "embedding_refresh", "report_generate", "sync_core_data"} | BUSINESS_TASK_KINDS
    if not can_dispatch:
        try:
            command_for_kind(kind)
            can_dispatch = True
        except Exception as exc:
            dispatch_error = str(exc)
    if can_dispatch:
        try:
            result = enqueue_task(kind, task_payload)
        except Exception as exc:
            dispatch_error = str(exc)
            result = create_pending_task_record(
                kind=kind,
                task_name=str(payload.get("task_name") or kind),
                payload=task_payload,
                queue_name=str(payload.get("queue_name") or ""),
                execution_mode="db_pending",
                created_by=getattr(user, "username", "web_user"),
            )
    else:
        result = create_pending_task_record(
            kind=kind,
            task_name=str(payload.get("task_name") or kind),
            payload=task_payload,
            queue_name=str(payload.get("queue_name") or ""),
            execution_mode="db_pending",
            created_by=getattr(user, "username", "web_user"),
        )
    if dispatch_error:
        result["dispatch_fallback_reason"] = dispatch_error[:300]
    write_audit_log(
        action="task.start",
        user=user,
        resource_type="task",
        resource_id=str(result.get("task_id") or kind),
        ip_address=request.client.host if request.client else "",
        metadata={"kind": kind, "task": result},
    )
    return result


@router.get("/api/task/recent")
def task_recent(limit: int = Query(default=8, ge=1, le=20)) -> dict:
    return task_recent_payload(limit=limit)


@router.get("/api/tasks/{task_id}")
def task_detail(task_id: str) -> dict:
    try:
        return task_manager.get(task_id)
    except KeyError:
        record = get_task_record(task_id)
        if record:
            return record
        raise HTTPException(status_code=404, detail="task not found") from None


@router.get("/api/tasks/{task_id}/logs")
def task_logs(
    task_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict:
    entries = list_task_log_entries(task_id, page=page, page_size=page_size)
    if entries is not None:
        return entries
    try:
        text_value = task_manager.logs(task_id)
    except KeyError:
        text_value = task_log_text(task_id)
    if text_value is None:
        raise HTTPException(status_code=404, detail="task not found")
    return {
        "task_id": task_id,
        "page": page,
        "page_size": page_size,
        "total": 1 if text_value else 0,
        "items": [{"level": "info", "step": "summary", "message": text_value}],
        "text": text_value,
    }


@router.post("/api/tasks/{task_id}/cancel")
def task_cancel(
    task_id: str,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("task:run"))],
    payload: dict | None = None,
) -> dict:
    cancel_reason = str((payload or {}).get("reason") or "cancel requested by user")[:500]
    record = get_task_record(task_id)
    if record:
        status = str(record.get("status") or "").lower()
        if status in {"success", "failed", "cancelled", "timeout"}:
            result = {"task_id": task_id, "status": status, "message": "task already finished"}
        elif status in {"pending", "queued"}:
            update_task_runtime_state(
                task_id,
                status="cancelled",
                message="cancelled before start",
                cancel_requested=True,
                cancel_reason=cancel_reason,
                finish=True,
            )
            append_task_log(task_id, level="warning", step="cleanup", message=cancel_reason, status="cancelled")
            result = {"task_id": task_id, "status": "cancelled", "message": "pending task cancelled", "cancel_reason": cancel_reason}
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
                cancel_reason=cancel_reason,
                metadata={"cancel_requested_by": getattr(user, "username", "system"), "cancel_reason": cancel_reason},
            )
            append_task_log(task_id, level="warning", step="cleanup", message=cancel_reason, status="cancel_requested")
            result = {"task_id": task_id, "status": "cancel_requested", "message": revoke_message, "cancel_reason": cancel_reason}
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
        raise HTTPException(status_code=404, detail="task not found") from None


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
    if status in {"running", "pending", "queued", "retrying", "cancel_requested"}:
        raise HTTPException(status_code=400, detail=f"task status {status} cannot be retried")
    if status not in {"failed", "cancelled", "timeout"}:
        raise HTTPException(status_code=400, detail=f"task status {status or 'unknown'} cannot be retried")
    kind = normalize_task_kind(str(record.get("kind") or record.get("task_kind") or record.get("task_name")))
    max_retries = int(record.get("max_retries") if record.get("max_retries") is not None else task_policy(kind).max_retries)
    retry_count = int(record.get("retry_count") or 0)
    if retry_count >= max_retries:
        raise HTTPException(status_code=400, detail=f"task retry limit exceeded: {retry_count}/{max_retries}")
    payload = dict(record.get("payload") or {})
    payload["retry_of"] = task_id
    payload["parent_task_id"] = task_id
    payload["original_task_id"] = record.get("original_task_id") or task_id
    payload["retry_count"] = retry_count + 1
    payload["force_new"] = True
    try:
        result = enqueue_task(kind, payload)
    except Exception as exc:
        result = create_pending_task_record(
            kind=kind,
            task_name=str(record.get("task_name") or kind),
            payload=payload,
            queue_name=str(record.get("queue_name") or ""),
            execution_mode="db_pending_retry",
            created_by=getattr(user, "username", "web_user"),
            retry_of=task_id,
        )
        result["dispatch_fallback_reason"] = str(exc)[:300]
    append_task_log(
        task_id,
        level="info",
        step="prepare",
        message=f"retry created: {result.get('task_id')}",
        status=status,
        metadata={"retry_task_id": result.get("task_id")},
    )
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

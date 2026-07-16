from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from ....core.security import CurrentUser, require_permission
from ....data_access import report_status
from ....platform_services import list_report_reviews, save_report_review
from ....repositories.audit_repository import write_audit_log
from ....repositories.report_repository import list_reports_from_postgres, report_summary_from_postgres
from ....schemas import ReportGenerateRequest, ReviewRequest
from ....source_contract import SourceType, attach_source_meta, source_meta
from ....workers.dispatcher import enqueue_task


router = APIRouter()


def _with_report_meta(payload: dict, *, historical: bool = False) -> dict:
    items = payload.get("items") or []
    available = bool(payload.get("available", payload.get("report_id") or items))
    item = items[0] if items else payload
    return attach_source_meta(
        payload,
        source_meta(
            SourceType.HISTORICAL if historical and available else (SourceType.REAL if available else SourceType.UNAVAILABLE),
            "report",
            run_id=item.get("run_id"),
            generated_at=item.get("generated_at") or item.get("updated_at") or item.get("created_at"),
            evidence=[{"table": "report_runs", "report_id": item.get("report_id")}],
            unavailable_reason=None if available else payload.get("unavailable_reason") or "report_not_found",
        ),
    )


@router.post("/api/reports/generate")
def report_generate(
    payload: ReportGenerateRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("report:generate"))],
) -> dict:
    try:
        result = enqueue_task("report_generate", {"run_id": payload.run_id})
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    write_audit_log(
        action="report.generate",
        user=user,
        resource_type="report",
        resource_id=str(result.get("task_id") or payload.run_id),
        ip_address=request.client.host if request.client else "",
        metadata={"run_id": payload.run_id, "task": result},
    )
    return result


@router.get("/api/reports")
def report_list(
    _: Annotated[CurrentUser, Depends(require_permission("report:read"))],
    keyword: str = Query(default="", max_length=128),
    report_type: str = Query(default="", max_length=64),
    status_value: str = Query(default="", alias="status", max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    payload = list_reports_from_postgres(keyword=keyword, report_type=report_type, status=status_value, page=page, page_size=page_size)
    if payload is None:
        latest = report_status()
        item = latest if latest.get("report_id") else None
        return _with_report_meta({
            "items": [item] if item else [],
            "total": 1 if item else 0,
            "page": page,
            "page_size": page_size,
            "source": latest.get("source") or "report_status",
        }, historical=True)
    return _with_report_meta(payload, historical=True)


@router.get("/api/reports/summary")
def report_summary(_: Annotated[CurrentUser, Depends(require_permission("report:read"))]) -> dict:
    payload = report_summary_from_postgres()
    if payload is not None:
        return _with_report_meta(payload, historical=True)
    latest = report_status()
    available = bool(latest.get("report_id"))
    return _with_report_meta({
        "today_generated": 1 if available else 0,
        "pending_review": 1 if available and latest.get("status") not in {"approved", "published", "rejected"} else 0,
        "published": 1 if latest.get("status") == "published" else 0,
        "rejected": 1 if latest.get("status") == "rejected" else 0,
        "total": 1 if available else 0,
        "source": latest.get("source") or "report_status",
    }, historical=True)


@router.get("/api/reports/latest")
def report_latest() -> dict:
    return _with_report_meta(report_status())


@router.get("/api/reports/{report_id}")
def report_detail(report_id: str) -> dict:
    return _with_report_meta(report_status(report_id), historical=True)


@router.get("/api/reports/{report_id}/download")
def report_download(report_id: str):
    report = report_status(report_id)
    path = Path(str(report.get("report_path") or ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="报告文件不存在")
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=path.name)


@router.post("/api/reports/{report_id}/regenerate")
def report_regenerate(
    report_id: str,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("report:generate"))],
) -> dict:
    try:
        result = enqueue_task("report_generate", {"report_id": report_id})
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    write_audit_log(
        action="report.regenerate",
        user=user,
        resource_type="report",
        resource_id=report_id,
        ip_address=request.client.host if request.client else "",
        metadata=result,
    )
    return result


@router.post("/api/reports/{report_id}/approve")
def report_approve(
    report_id: str,
    payload: ReviewRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("report:review"))],
) -> dict:
    result = save_report_review(report_id, "approved", payload.reviewer, payload.review_comment)
    write_audit_log(
        action="report.approve",
        user=user,
        resource_type="report",
        resource_id=report_id,
        ip_address=request.client.host if request.client else "",
        metadata={"reviewer": payload.reviewer, "result": result},
    )
    return result


@router.post("/api/reports/{report_id}/reject")
def report_reject(
    report_id: str,
    payload: ReviewRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("report:review"))],
) -> dict:
    if not payload.review_comment.strip():
        raise HTTPException(status_code=400, detail="驳回报告必须填写审核意见")
    result = save_report_review(report_id, "rejected", payload.reviewer, payload.review_comment)
    write_audit_log(
        action="report.reject",
        user=user,
        resource_type="report",
        resource_id=report_id,
        status="success",
        ip_address=request.client.host if request.client else "",
        metadata={"reviewer": payload.reviewer, "comment": payload.review_comment, "result": result},
    )
    return result


@router.post("/api/reports/{report_id}/publish")
def report_publish(
    report_id: str,
    payload: ReviewRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("report:review"))],
) -> dict:
    result = save_report_review(report_id, "published", payload.reviewer, payload.review_comment)
    write_audit_log(
        action="report.publish",
        user=user,
        resource_type="report",
        resource_id=report_id,
        ip_address=request.client.host if request.client else "",
        metadata={"reviewer": payload.reviewer, "result": result},
    )
    return result


@router.get("/api/reports/{report_id}/reviews")
def report_reviews(report_id: str) -> dict:
    return {"report_id": report_id, "reviews": list_report_reviews(report_id)}

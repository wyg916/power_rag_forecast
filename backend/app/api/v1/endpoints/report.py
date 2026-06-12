from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from ....core.security import CurrentUser, require_permission
from ....data_access import report_status
from ....platform_services import list_report_reviews, save_report_review
from ....repositories.audit_repository import write_audit_log
from ....schemas import ReportGenerateRequest, ReviewRequest
from ....workers.dispatcher import enqueue_task


router = APIRouter()


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


@router.get("/api/reports/latest")
def report_latest() -> dict:
    return report_status()


@router.get("/api/reports/{report_id}")
def report_detail(report_id: str) -> dict:
    return report_status(report_id)


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

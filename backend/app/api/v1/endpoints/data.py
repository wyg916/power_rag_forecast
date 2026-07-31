from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response

from ....core.security import CurrentUser, require_permission
from ....repositories.audit_repository import write_audit_log
from ....schemas import (
    DataCatalogResponse,
    DataFreshnessResponse,
    DataQualityResponse,
    DataStatusResponse,
    DataSyncRecordsResponse,
    DatasetListResponse,
    DatasetRowsResponse,
)
from ....services.dataset_query_service import (
    DatasetQueryError,
    dataset_fields,
    dataset_freshness,
    dataset_quality_report,
    dataset_status,
    export_dataset_csv,
    list_registered_datasets,
    query_dataset_rows,
)
from ....services.ui_platform_service import import_export_records
from ....source_contract import SourceType, attach_source_meta, source_meta
from ....workers.dispatcher import enqueue_task


router = APIRouter()
logger = logging.getLogger(__name__)


def _with_data_meta(payload: dict, *, evidence: str) -> dict:
    available = bool(payload.get("available", payload.get("sources") or payload.get("datasets") or payload.get("records")))
    return attach_source_meta(
        payload,
        source_meta(
            SourceType.DERIVED if available else SourceType.UNAVAILABLE,
            "data_quality",
            generated_at=payload.get("generated_at") or payload.get("updated_at") or payload.get("checked_at"),
            is_stale=bool(payload.get("is_stale")),
            stale_reason=payload.get("stale_reason"),
            evidence=[{"source": evidence, "read_only": True}],
            unavailable_reason=None if available else payload.get("unavailable_reason") or "data_source_empty",
        ),
    )


def _query_error(exc: DatasetQueryError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _log_read_event(
    request: Request,
    user: CurrentUser,
    *,
    action: str,
    dataset_id: str,
    row_count: int | None = None,
    search_applied: bool = False,
    filter_field: str = "",
    filter_operator: str = "",
) -> None:
    logger.info(
        "data_access action=%s user_id=%s role=%s dataset_id=%s row_count=%s search_applied=%s filter_field=%s filter_operator=%s request_id=%s",
        action,
        user.user_id,
        user.role,
        dataset_id,
        row_count if row_count is not None else "",
        search_applied,
        filter_field,
        filter_operator,
        request.headers.get("x-request-id", ""),
    )


@router.get("/api/data/status", response_model=DataStatusResponse)
def get_data_status(_: Annotated[CurrentUser, Depends(require_permission("data:read"))]) -> dict:
    try:
        return _with_data_meta(dataset_status(), evidence="registered datasets")
    except DatasetQueryError as exc:
        raise _query_error(exc) from exc


@router.get("/api/data/catalog", response_model=DataCatalogResponse)
def get_catalog(
    _: Annotated[CurrentUser, Depends(require_permission("data:read"))],
    search: str | None = None,
    include_runtime: bool = False,
) -> dict:
    return _with_data_meta(
        list_registered_datasets(search=search, include_runtime=include_runtime),
        evidence="static dataset registry",
    )


@router.get("/api/data/fields")
def get_fields(
    _: Annotated[CurrentUser, Depends(require_permission("data:read"))],
    dataset_id: str,
    search: str | None = None,
) -> dict:
    try:
        return _with_data_meta(dataset_fields(dataset_id=dataset_id, search=search), evidence="registered field contract")
    except DatasetQueryError as exc:
        raise _query_error(exc) from exc


@router.get("/api/data/freshness", response_model=DataFreshnessResponse)
def get_freshness(
    _: Annotated[CurrentUser, Depends(require_permission("data:read"))],
    dataset_ids: list[str] | None = Query(default=None),
) -> dict:
    try:
        return _with_data_meta(dataset_freshness(dataset_ids=dataset_ids), evidence="controlled dataset aggregates")
    except DatasetQueryError as exc:
        raise _query_error(exc) from exc


@router.post("/api/data/sql/query", status_code=status.HTTP_410_GONE)
def query_arbitrary_sql_disabled(
    _: Annotated[CurrentUser, Depends(require_permission("data:query"))],
) -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={"code": "arbitrary_sql_disabled", "message": "任意 SQL 查询接口已永久禁用，请使用已注册数据集接口。"},
    )


@router.get("/api/data/datasets", response_model=DatasetListResponse)
def get_datasets(
    _: Annotated[CurrentUser, Depends(require_permission("data:read"))],
    search: str | None = None,
) -> dict:
    return _with_data_meta(list_registered_datasets(search=search, include_runtime=True), evidence="static dataset registry")


@router.get("/api/data/datasets/{dataset_id}/rows", response_model=DatasetRowsResponse)
def get_dataset_rows(
    request: Request,
    dataset_id: str,
    user: Annotated[CurrentUser, Depends(require_permission("data:read"))],
    search: str | None = None,
    filter_field: str | None = None,
    filter_operator: Literal["eq", "contains", "gte", "lte"] = "eq",
    filter_value: str | None = None,
    sort: str | None = None,
    direction: Literal["asc", "desc"] | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    try:
        payload = query_dataset_rows(
            dataset_id,
            search=search,
            filter_field=filter_field,
            filter_operator=filter_operator,
            filter_value=filter_value,
            sort=sort,
            direction=direction,
            page=page,
            page_size=page_size,
        )
    except DatasetQueryError as exc:
        raise _query_error(exc) from exc
    _log_read_event(
        request,
        user,
        action="rows",
        dataset_id=payload["dataset_id"],
        row_count=len(payload["records"]),
        search_applied=payload["search_applied"],
        filter_field=filter_field or "",
        filter_operator=filter_operator if filter_field else "",
    )
    return _with_data_meta(payload, evidence=f"dataset:{payload['dataset_id']}")


@router.get("/api/data/quality", response_model=DataQualityResponse)
def get_data_quality(_: Annotated[CurrentUser, Depends(require_permission("data:read"))]) -> dict:
    try:
        return _with_data_meta(dataset_quality_report(), evidence="controlled dataset quality aggregates")
    except DatasetQueryError as exc:
        raise _query_error(exc) from exc


@router.get("/api/data/import-export-records", response_model=DataSyncRecordsResponse)
def get_import_export_records(
    _: Annotated[CurrentUser, Depends(require_permission("data:read"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
) -> dict:
    return _with_data_meta(import_export_records(page=page, page_size=page_size), evidence="controlled task history")


@router.get("/api/data/datasets/{dataset_id}/export")
def export_dataset(
    request: Request,
    dataset_id: str,
    user: Annotated[CurrentUser, Depends(require_permission("data:export"))],
    search: str | None = None,
    filter_field: str | None = None,
    filter_operator: Literal["eq", "contains", "gte", "lte"] = "eq",
    filter_value: str | None = None,
    sort: str | None = None,
    direction: Literal["asc", "desc"] | None = None,
) -> Response:
    try:
        export = export_dataset_csv(
            dataset_id,
            search=search,
            filter_field=filter_field,
            filter_operator=filter_operator,
            filter_value=filter_value,
            sort=sort,
            direction=direction,
        )
    except DatasetQueryError as exc:
        raise _query_error(exc) from exc
    _log_read_event(
        request,
        user,
        action="export",
        dataset_id=dataset_id,
        row_count=export["row_count"],
        search_applied=bool(str(search or "").strip()),
        filter_field=filter_field or "",
        filter_operator=filter_operator if filter_field else "",
    )
    return Response(
        content=export["content"],
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{export["filename"]}"',
            "X-Export-Row-Count": str(export["row_count"]),
            "X-Export-Total": str(export["total"]),
            "X-Export-Truncated": "true" if export["truncated"] else "false",
        },
    )


@router.post("/api/data/refresh")
def refresh_data(
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("data:sync"))],
) -> dict:
    result = enqueue_task("refresh_data")
    write_audit_log(
        action="data.refresh",
        user=user,
        resource_type="data_sync",
        resource_id=str(result.get("task_id") or "refresh_data"),
        ip_address=request.client.host if request.client else "",
        metadata=result,
    )
    return result


@router.post("/api/data/sync-core")
def sync_core_data_to_database(
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("data:sync"))],
) -> dict:
    result = enqueue_task("sync_core_data")
    write_audit_log(
        action="data.sync_core",
        user=user,
        resource_type="data_sync",
        resource_id=str(result.get("task_id") or "sync_core_data"),
        ip_address=request.client.host if request.client else "",
        metadata=result,
    )
    return result

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from ....core.security import CurrentUser, require_permission
from ....data_access import data_status, database_table_rows, database_tables
from ....repositories.audit_repository import write_audit_log
from ....schemas import (
    DataCatalogResponse,
    DataFreshnessResponse,
    DataQualityResponse,
    DataStatusResponse,
    DataSyncRecordsResponse,
    DatabaseTableRowsResponse,
    DatabaseTablesResponse,
    ReadOnlySqlRequest,
)
from ....services.data_trust_service import execute_read_only_sql, get_data_catalog, get_data_freshness_report, get_field_mappings
from ....services.ui_platform_service import data_quality_report, export_table_to_csv, import_export_records
from ....source_contract import SourceType, attach_source_meta, source_meta
from ....workers.dispatcher import enqueue_task


router = APIRouter()


def _with_data_meta(payload: dict, *, evidence: str) -> dict:
    available = bool(payload.get("available", payload.get("sources") or payload.get("tables") or payload.get("datasets") or payload.get("records")))
    return attach_source_meta(
        payload,
        source_meta(
            SourceType.DERIVED if available else SourceType.UNAVAILABLE,
            "data_quality",
            generated_at=payload.get("generated_at") or payload.get("updated_at"),
            is_stale=bool(payload.get("is_stale")),
            stale_reason=payload.get("stale_reason"),
            evidence=[{"source": evidence, "read_only": True}],
            unavailable_reason=None if available else payload.get("unavailable_reason") or "data_source_empty",
        ),
    )


@router.get("/api/data/status", response_model=DataStatusResponse)
def get_data_status(_: Annotated[CurrentUser, Depends(require_permission("data:read"))]) -> dict:
    return _with_data_meta(data_status(), evidence="postgresql core data tables")


@router.get("/api/data/catalog", response_model=DataCatalogResponse)
def get_catalog(
    _: Annotated[CurrentUser, Depends(require_permission("data:read"))],
    search: str | None = None,
    include_runtime: bool = False,
) -> dict:
    return _with_data_meta(get_data_catalog(search=search, include_runtime=include_runtime), evidence="data catalog")


@router.get("/api/data/fields")
def get_fields(
    _: Annotated[CurrentUser, Depends(require_permission("data:read"))],
    table: str | None = None,
    search: str | None = None,
) -> dict:
    return _with_data_meta(get_field_mappings(table=table, search=search), evidence="field mappings")


@router.get("/api/data/freshness", response_model=DataFreshnessResponse)
def get_freshness(
    _: Annotated[CurrentUser, Depends(require_permission("data:read"))],
    tables: list[str] | None = Query(default=None),
) -> dict:
    return _with_data_meta(get_data_freshness_report(tables=tables), evidence="postgresql freshness queries")


@router.post("/api/data/sql/query")
def query_read_only_sql(
    payload: ReadOnlySqlRequest,
    _: Annotated[CurrentUser, Depends(require_permission("data:read"))],
) -> dict:
    return execute_read_only_sql(sql=payload.sql, params=payload.params, limit=payload.limit)


@router.get("/api/data/tables", response_model=DatabaseTablesResponse)
def get_database_tables(
    _: Annotated[CurrentUser, Depends(require_permission("data:read"))],
    search: str | None = None,
) -> dict:
    return _with_data_meta(database_tables(search=search), evidence="information_schema")


@router.get("/api/data/tables/{table_name}/rows", response_model=DatabaseTableRowsResponse)
def get_database_table_rows(
    table_name: str,
    _: Annotated[CurrentUser, Depends(require_permission("data:read"))],
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int | None = Query(default=None, ge=0),
) -> dict:
    effective_size = limit or page_size
    effective_offset = offset if offset is not None else (page - 1) * page_size
    return _with_data_meta(
        database_table_rows(table_name=table_name, search=search, limit=effective_size, offset=effective_offset),
        evidence=f"postgresql.{table_name}",
    )


@router.get("/api/data/quality", response_model=DataQualityResponse)
def get_data_quality(_: Annotated[CurrentUser, Depends(require_permission("data:read"))]) -> dict:
    return _with_data_meta(data_quality_report(), evidence="postgresql quality aggregates")


@router.get("/api/data/import-export-records", response_model=DataSyncRecordsResponse)
def get_import_export_records(
    _: Annotated[CurrentUser, Depends(require_permission("data:read"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
) -> dict:
    return _with_data_meta(import_export_records(page=page, page_size=page_size), evidence="postgresql.task_runs")


@router.get("/api/data/tables/{table_name}/export")
def export_database_table(
    table_name: str,
    _: Annotated[CurrentUser, Depends(require_permission("data:read"))],
    search: str | None = None,
):
    export = export_table_to_csv(table_name, search=search)
    if not export.get("available"):
        return Response(
            content=str(export.get("message") or "数据库对象不可用"),
            status_code=404,
            media_type="text/plain; charset=utf-8",
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

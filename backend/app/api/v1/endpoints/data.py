from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse

from ....core.security import CurrentUser, require_permission
from ....data_access import data_status, database_table_rows, database_tables
from ....repositories.audit_repository import write_audit_log
from ....schemas import ReadOnlySqlRequest
from ....services.data_trust_service import execute_read_only_sql, get_data_catalog, get_data_freshness_report, get_field_mappings
from ....services.ui_platform_service import data_quality_report, export_table_to_csv, import_export_records, response
from ....workers.dispatcher import enqueue_task


router = APIRouter()


@router.get("/api/data/status")
def get_data_status() -> dict:
    return data_status()


@router.get("/api/data/catalog")
def get_catalog(search: str | None = None, include_runtime: bool = False) -> dict:
    return get_data_catalog(search=search, include_runtime=include_runtime)


@router.get("/api/data/fields")
def get_fields(table: str | None = None, search: str | None = None) -> dict:
    return get_field_mappings(table=table, search=search)


@router.get("/api/data/freshness")
def get_freshness(tables: list[str] | None = Query(default=None)) -> dict:
    return get_data_freshness_report(tables=tables)


@router.post("/api/data/sql/query")
def query_read_only_sql(
    payload: ReadOnlySqlRequest,
    _: Annotated[CurrentUser, Depends(require_permission("data:read"))],
) -> dict:
    return execute_read_only_sql(sql=payload.sql, params=payload.params, limit=payload.limit)


@router.get("/api/data/tables")
def get_database_tables(search: str | None = None) -> dict:
    return database_tables(search=search)


@router.get("/api/data/tables/{table_name}/rows")
def get_database_table_rows(table_name: str, search: str | None = None, limit: int = 100, offset: int = 0) -> dict:
    return database_table_rows(table_name=table_name, search=search, limit=limit, offset=offset)


@router.get("/api/data/quality")
def get_data_quality() -> dict:
    return response(data_quality_report(), data_source="postgresql_or_file")


@router.get("/api/data/import-export-records")
def get_import_export_records() -> dict:
    return response(import_export_records(), data_source="postgresql.task_runs")


@router.get("/api/data/tables/{table_name}/export")
def export_database_table(table_name: str, search: str | None = None):
    path = export_table_to_csv(table_name, search=search)
    return FileResponse(path, media_type="text/csv", filename=path.name)


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

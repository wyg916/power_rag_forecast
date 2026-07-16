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
            evidence=[{"source": evidence, "read_only": True}],
            unavailable_reason=None if available else "data_source_empty",
        ),
    )


@router.get("/api/data/status")
def get_data_status() -> dict:
    return _with_data_meta(data_status(), evidence="postgresql core data tables")


@router.get("/api/data/catalog")
def get_catalog(search: str | None = None, include_runtime: bool = False) -> dict:
    return _with_data_meta(get_data_catalog(search=search, include_runtime=include_runtime), evidence="data catalog")


@router.get("/api/data/fields")
def get_fields(table: str | None = None, search: str | None = None) -> dict:
    return _with_data_meta(get_field_mappings(table=table, search=search), evidence="field mappings")


@router.get("/api/data/freshness")
def get_freshness(tables: list[str] | None = Query(default=None)) -> dict:
    return _with_data_meta(get_data_freshness_report(tables=tables), evidence="postgresql freshness queries")


@router.post("/api/data/sql/query")
def query_read_only_sql(
    payload: ReadOnlySqlRequest,
    _: Annotated[CurrentUser, Depends(require_permission("data:read"))],
) -> dict:
    return execute_read_only_sql(sql=payload.sql, params=payload.params, limit=payload.limit)


@router.get("/api/data/tables")
def get_database_tables(search: str | None = None) -> dict:
    return _with_data_meta(database_tables(search=search), evidence="information_schema")


@router.get("/api/data/tables/{table_name}/rows")
def get_database_table_rows(table_name: str, search: str | None = None, limit: int = 100, offset: int = 0) -> dict:
    return _with_data_meta(
        database_table_rows(table_name=table_name, search=search, limit=limit, offset=offset),
        evidence=f"postgresql.{table_name}",
    )


@router.get("/api/data/quality")
def get_data_quality() -> dict:
    return _with_data_meta(response(data_quality_report(), data_source="postgresql"), evidence="postgresql quality aggregates")


@router.get("/api/data/import-export-records")
def get_import_export_records() -> dict:
    return _with_data_meta(response(import_export_records(), data_source="postgresql.task_runs"), evidence="postgresql.task_runs")


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

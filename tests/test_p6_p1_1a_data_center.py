from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.data_access import database_engine
from backend.app.core.config import get_settings
from backend.app.main import app
from backend.app.services.ui_platform_service import QUALITY_DATASETS, data_quality_report, import_export_records


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _protected_counts() -> dict[str, int]:
    engine = database_engine()
    assert engine is not None
    with engine.connect() as conn:
        return {
            table: int(conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0)
            for table in ("raw_weather", "task_runs", "task_logs", "audit_logs")
        }


def test_database_target_is_the_authorized_local_postgres():
    engine = database_engine()
    assert engine is not None
    assert engine.dialect.name == "postgresql"
    assert engine.url.host == "localhost"
    assert int(engine.url.port or 5432) == 5432
    assert engine.url.database == "postgres"


def test_quality_and_sync_reads_do_not_write_protected_tables():
    before = _protected_counts()
    quality = data_quality_report()
    sync_records = import_export_records(page=1, page_size=8)
    after = _protected_counts()

    assert before == after
    assert quality["available"] is True
    assert sync_records["available"] is True


def test_quality_report_uses_real_metrics_and_explicit_stale_semantics():
    payload = data_quality_report()
    items = payload["items"]

    assert len(items) == len(QUALITY_DATASETS)
    assert payload["generated_at"]
    assert isinstance(payload["is_stale"], bool)
    assert payload["summary"]["checked_source_count"] == len(QUALITY_DATASETS)
    for row in items:
        for field in (
            "table_name",
            "status",
            "missing_rate",
            "duplicate_rate",
            "freshness_score",
            "consistency_score",
            "check_pass_rate",
            "data_source",
            "is_stale",
        ):
            assert field in row
        if row["available"] and row["rows"]:
            assert row["duplicate_rate"] is not None
            assert row["consistency_score"] is not None
    assert any(row["status"] == "missing_table" for row in items)
    assert any(row["is_stale"] for row in items)
    assert payload["alerts"]


def test_sync_records_are_server_paginated_and_missing_metrics_stay_null():
    first = import_export_records(page=1, page_size=5)
    second = import_export_records(page=2, page_size=5)

    assert first["pagination"]["page"] == 1
    assert first["pagination"]["page_size"] == 5
    assert len(first["records"]) <= 5
    assert len(second["records"]) <= 5
    assert first["pagination"]["total"] >= len(first["records"])
    for row in first["records"]:
        for field in (
            "record_id",
            "run_id",
            "started_at",
            "ended_at",
            "processed_rows",
            "success_rows",
            "failed_rows",
            "data_source",
        ):
            assert field in row
        if row["processed_rows"] is None:
            assert row["status_reason"] == "当前任务记录未保存处理行数"


def test_data_center_read_api_has_real_meta_pagination_and_permission(monkeypatch):
    overview_responses = [
        client.get("/api/data/status"),
        client.get("/api/data/catalog?include_runtime=true"),
        client.get("/api/data/freshness"),
        client.get("/api/data/tables"),
    ]
    quality_response = client.get("/api/data/quality")
    records_response = client.get("/api/data/import-export-records?page=1&page_size=4")
    forbidden_response = client.get(
        "/api/data/quality",
        headers={"X-User": "p6_reviewer", "X-Role": "reviewer"},
    )

    assert all(response.status_code == 200 for response in overview_responses)
    assert quality_response.status_code == 200
    assert records_response.status_code == 200
    assert forbidden_response.status_code == 403
    quality = quality_response.json()
    records = records_response.json()
    assert quality["source_type"] == "derived"
    assert quality["generated_at"]
    assert quality["meta"]["is_stale"] == quality["is_stale"]
    assert records["pagination"] == {"page": 1, "page_size": 4, "total": records["pagination"]["total"]}
    assert len(records["records"]) <= 4

    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("JWT_SECRET_KEY", "p6-p1-1a-test-secret-key-32-chars")
    get_settings.cache_clear()
    try:
        unauthorized_response = client.get("/api/data/quality")
        assert unauthorized_response.status_code == 401
    finally:
        monkeypatch.setenv("AUTH_REQUIRED", "0")
        get_settings.cache_clear()


def test_no_static_quality_success_or_response_wrapper_regression():
    service = _read("backend/app/services/ui_platform_service.py")
    endpoint = _read("backend/app/api/v1/endpoints/data.py")

    assert '"duplicate_rate": 0' not in service
    assert '100 if item.get("latest_time")' not in service
    assert "response(data_quality_report()" not in endpoint
    assert "response(import_export_records()" not in endpoint
    assert 'require_permission("data:read")' in endpoint
    assert "response_model=DataStatusResponse" in endpoint
    assert "response_model=DataCatalogResponse" in endpoint
    assert "response_model=DataFreshnessResponse" in endpoint
    assert "response_model=DatabaseTablesResponse" in endpoint
    assert "response_model=DataQualityResponse" in endpoint
    assert "response_model=DataSyncRecordsResponse" in endpoint


def test_frontend_preserves_null_metrics_and_uses_real_pagination():
    api = _read("frontend/src/api.ts")
    service = _read("frontend/src/services/dataApi.ts")
    page = _read("frontend/src/pages/data/DataCenterPage.tsx")
    design = _read("frontend/src/components/data/DataCenterDesign.tsx")

    assert "page_size" in api
    assert "processedRows: row.processed_rows ?? null" in service
    assert "Number(row.rows || row.row_count || 0)" not in service
    assert "syncPagination" in service
    assert "onPageChange={setSyncPage}" in page
    assert "pagination={{" in design
    assert "processedRows" in design and "successRows" in design and "failedRows" in design
    assert "mockFallback: false" in service


def test_data_center_actions_and_alert_details_are_real():
    page = _read("frontend/src/pages/data/DataCenterPage.tsx")
    design = _read("frontend/src/components/data/DataCenterDesign.tsx")

    assert "api.dataRefresh()" in page
    assert "onClick: loadData" in page
    assert "data:sync" in page
    assert "disabled: !canSync" in page
    assert "alertId: item.alert_id" in design
    assert "onDetail({" in design
    assert "快捷操作" not in design


def test_data_center_internal_scroll_and_no_fact_status_bar_regression():
    page = _read("frontend/src/pages/data/DataCenterPage.tsx")
    design = _read("frontend/src/components/data/DataCenterDesign.tsx")
    styles = _read("frontend/src/styles.css")

    assert "FactStatusBar" not in page
    assert "scroll={{ y: 205, x: 1280 }}" in design
    assert "scroll={{ y: 205, x: 1120 }}" in design
    assert ".data-design-page" in styles
    assert "overflow: hidden;" in styles
    assert "@media (max-height: 850px) and (min-width: 1181px)" in styles

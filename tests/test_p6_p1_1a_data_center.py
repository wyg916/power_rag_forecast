from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.core.config import get_settings
from backend.app.data_access import database_engine
from backend.app.main import app
from backend.app.services.dataset_query_service import dataset_quality_report
from backend.app.services.ui_platform_service import import_export_records


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)
ANALYST = {"X-User": "p6_analyst", "X-Role": "analyst"}


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _protected_counts() -> dict[str, int]:
    runtime = database_engine()
    assert runtime is not None
    with runtime.connect() as conn:
        values = {
            table: int(conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0)
            for table in ("raw_weather", "task_runs", "task_logs")
        }
    return values


def test_database_target_is_the_authorized_local_postgres_and_not_superuser():
    engine = database_engine()
    assert engine is not None and engine.dialect.name == "postgresql"
    assert engine.url.host == "localhost"
    assert int(engine.url.port or 5432) == 5432
    assert engine.url.database == "postgres"
    with engine.connect() as conn:
        role = conn.execute(text("SELECT current_user, rolsuper FROM pg_roles WHERE rolname=current_user")).one()
    assert role[1] is False


def test_quality_and_sync_reads_do_not_write_protected_tables():
    before = _protected_counts()
    quality = dataset_quality_report()
    sync_records = import_export_records(page=1, page_size=8)
    assert _protected_counts() == before
    assert quality["available"] is True
    assert sync_records["available"] is True


def test_quality_report_uses_registered_dataset_contract():
    payload = dataset_quality_report()
    assert payload["generated_at"]
    assert payload["summary"]["checked_source_count"] == 11
    assert len(payload["items"]) == 11
    for row in payload["items"]:
        assert row["dataset_id"]
        assert "table_name" not in row
        assert "missing_rate" in row
        assert "consistency_score" in row


def test_sync_records_are_server_paginated_and_missing_metrics_stay_null():
    first = import_export_records(page=1, page_size=5)
    second = import_export_records(page=2, page_size=5)
    assert first["pagination"]["page"] == 1
    assert second["pagination"]["page"] == 2
    assert len(first["records"]) <= 5 and len(second["records"]) <= 5
    for row in first["records"]:
        if row["processed_rows"] is None:
            assert row["status_reason"] == "当前任务记录未保存处理行数"


def test_data_center_read_api_has_dataset_meta_pagination_and_permission(monkeypatch):
    overview = [
        client.get("/api/data/status", headers=ANALYST),
        client.get("/api/data/catalog?include_runtime=true", headers=ANALYST),
        client.get("/api/data/freshness", headers=ANALYST),
        client.get("/api/data/datasets", headers=ANALYST),
    ]
    quality_response = client.get("/api/data/quality", headers=ANALYST)
    records_response = client.get("/api/data/import-export-records?page=1&page_size=4", headers=ANALYST)
    forbidden = client.get("/api/data/quality", headers={"X-User": "p6_reviewer", "X-Role": "reviewer"})
    assert all(response.status_code == 200 for response in overview)
    assert quality_response.status_code == 200
    assert records_response.status_code == 200
    assert forbidden.status_code == 403
    assert overview[-1].json()["datasets"]
    assert all("table_name" not in item for item in overview[-1].json()["datasets"])

    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("JWT_SECRET_KEY", "p6-p1-1a-test-secret-key-32-chars")
    get_settings.cache_clear()
    try:
        assert client.get("/api/data/quality").status_code == 401
    finally:
        monkeypatch.setenv("AUTH_REQUIRED", "0")
        get_settings.cache_clear()


def test_backend_uses_dataset_response_models_and_no_dynamic_browser_routes():
    endpoint = _read("backend/app/api/v1/endpoints/data.py")
    assert "response_model=DatasetListResponse" in endpoint
    assert "response_model=DatasetRowsResponse" in endpoint
    assert 'require_permission("data:read")' in endpoint
    assert "/api/data/tables" not in endpoint
    assert "query_arbitrary_sql_disabled" in endpoint


def test_frontend_preserves_null_metrics_and_uses_real_pagination():
    api = _read("frontend/src/api.ts")
    service = _read("frontend/src/services/dataApi.ts")
    page = _read("frontend/src/pages/data/DataCenterPage.tsx")
    design = _read("frontend/src/components/data/DataCenterDesign.tsx")
    assert "page_size" in api
    assert "processedRows: row.processed_rows ?? null" in service
    assert "syncPagination" in service
    assert "onPageChange={setSyncPage}" in page
    assert "pagination={{" in design
    assert "mockFallback: false" in service


def test_data_center_actions_and_alert_details_are_real():
    page = _read("frontend/src/pages/data/DataCenterPage.tsx")
    design = _read("frontend/src/components/data/DataCenterDesign.tsx")
    assert "api.dataRefresh()" in page
    assert "data:sync" in page and "data:export" in page
    assert "disabled: !canSync" in page
    assert "alertId: item.alert_id" in design


def test_data_center_internal_scroll_and_no_fact_status_bar_regression():
    page = _read("frontend/src/pages/data/DataCenterPage.tsx")
    design = _read("frontend/src/components/data/DataCenterDesign.tsx")
    styles = _read("frontend/src/styles.css")
    assert "FactStatusBar" not in page
    assert "scroll={{ y: 205, x: 1120 }}" in design
    assert ".data-design-page" in styles
    assert "@media (max-height: 850px) and (min-width: 1181px)" in styles

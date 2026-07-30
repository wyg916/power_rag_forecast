from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.core.config import get_settings
from backend.app.data_access import database_engine, database_table_rows
from backend.app.main import app
from backend.app.services.ui_platform_service import export_table_to_csv, import_export_records
from tests.test_p6_p1_1a_data_center import _protected_counts


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_database_target_and_catalog_reads_remain_read_only():
    engine = database_engine()
    assert engine is not None
    assert engine.dialect.name == "postgresql"
    assert engine.url.host == "localhost"
    assert int(engine.url.port or 5432) == 5432
    assert engine.url.database == "postgres"

    before = _protected_counts()
    database_table_rows("raw_market", limit=5, offset=0)
    database_table_rows("raw_da_price", limit=5, offset=0)
    import_export_records(page=1, page_size=4)
    export_table_to_csv("forecast_results", max_rows=10)
    assert _protected_counts() == before


def test_table_and_view_use_stable_database_pagination():
    first = database_table_rows("raw_market", limit=5, offset=0)
    second = database_table_rows("raw_market", limit=5, offset=5)
    view = database_table_rows("raw_da_price", limit=5, offset=0)

    assert first["available"] is True
    assert first["object_type"] == "table"
    assert first["order_by"] == "id"
    assert first["pagination"] == {"page": 1, "page_size": 5, "total": first["total"]}
    assert {row["id"] for row in first["records"]}.isdisjoint({row["id"] for row in second["records"]})
    assert [row["id"] for row in first["records"]] == sorted(
        [row["id"] for row in first["records"]], reverse=True
    )

    assert view["available"] is True
    assert view["object_type"] == "view"
    assert view["order_by"] == "datetime"
    assert len(view["records"]) == 5


def test_table_search_empty_and_missing_object_semantics():
    filtered = database_table_rows("raw_market", search="DOM", limit=3, offset=0)
    empty = database_table_rows("raw_market", search="p6-no-such-catalog-value", limit=3, offset=0)
    missing = database_table_rows("model_master_table", limit=3, offset=0)

    assert filtered["available"] is True
    assert filtered["total"] > 0
    assert filtered["search"] == "DOM"
    assert empty["available"] is True
    assert empty["total"] == 0
    assert empty["records"] == []
    assert missing["available"] is False
    assert missing["total"] == 0
    assert "表或视图" in missing["message"]


def test_table_rows_api_has_response_model_permissions_and_canonical_pagination(monkeypatch):
    response = client.get("/api/data/tables/raw_da_price/rows?page=2&page_size=4")
    forbidden = client.get(
        "/api/data/tables/raw_market/rows?page=1&page_size=4",
        headers={"X-User": "p6_reviewer", "X-Role": "reviewer"},
    )

    assert response.status_code == 200
    assert forbidden.status_code == 403
    payload = response.json()
    assert payload["object_type"] == "view"
    assert payload["pagination"]["page"] == 2
    assert payload["pagination"]["page_size"] == 4
    assert len(payload["records"]) == 4
    assert payload["source_type"] == "derived"

    monkeypatch.setenv("AUTH_REQUIRED", "1")
    monkeypatch.setenv("JWT_SECRET_KEY", "p6-p1-1b-test-secret-key-32-chars")
    get_settings.cache_clear()
    try:
        unauthorized = client.get("/api/data/tables/raw_market/rows?page=1&page_size=4")
        assert unauthorized.status_code == 401
    finally:
        monkeypatch.setenv("AUTH_REQUIRED", "0")
        get_settings.cache_clear()


def test_export_is_authenticated_memory_csv_and_does_not_create_temp_file():
    export_dir = ROOT / "output" / "exports"
    before = sorted(path.name for path in export_dir.glob("*")) if export_dir.exists() else []
    response = client.get("/api/data/tables/forecast_results/export")
    after = sorted(path.name for path in export_dir.glob("*")) if export_dir.exists() else []

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["x-export-row-count"] == "24"
    assert response.headers["x-export-truncated"] == "false"
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert b"run_id" in response.content[:500]
    assert before == after


def test_sync_records_are_paginated_in_task_runs_query():
    first = import_export_records(page=1, page_size=4)
    second = import_export_records(page=2, page_size=4)
    ids_first = {row["record_id"] for row in first["records"]}
    ids_second = {row["record_id"] for row in second["records"]}
    engine = database_engine()
    assert engine is not None
    with engine.connect() as conn:
        expected_total = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM task_runs
                    WHERE LOWER(COALESCE(task_kind, '')) SIMILAR TO '%(sync|data|import|export|report)%'
                       OR LOWER(COALESCE(task_type, '')) SIMILAR TO '%(sync|data|import|export|report)%'
                       OR LOWER(COALESCE(task_name, '')) SIMILAR TO '%(sync|data|import|export|report)%'
                    """
                )
            ).scalar_one()
        )
    service = _read("backend/app/services/ui_platform_service.py")
    active = service.split("def import_export_records(", 1)[1].split("def export_table_to_csv(", 1)[0]

    assert first["pagination"]["total"] == second["pagination"]["total"] == expected_total
    assert first["pagination"]["page"] == 1
    assert second["pagination"]["page"] == 2
    assert ids_first.isdisjoint(ids_second)
    assert "list_task_runs(" in active
    assert "list_recent_tasks(" not in active


def test_backend_contract_has_no_database_creation_or_unbounded_export():
    files = [
        _read("backend/app/data_access.py"),
        _read("backend/app/repositories/task_repository.py"),
        _read("backend/app/services/ui_platform_service.py"),
        _read("backend/app/api/v1/endpoints/data.py"),
    ]
    combined = "\n".join(files).lower()
    endpoint = files[-1]

    assert "create database" not in combined
    assert "drop database" not in combined
    assert "truncate table" not in combined
    assert "response_model=databasetablerowsresponse" in endpoint.lower()
    assert "max_rows: int = 5000" in files[2]
    assert "export_dir.mkdir" not in files[2]


def test_frontend_catalog_preview_uses_real_api_states_pagination_and_blob_export():
    api = _read("frontend/src/api.ts")
    page = _read("frontend/src/pages/data/DataCenterPage.tsx")
    design = _read("frontend/src/components/data/DataCenterDesign.tsx")
    styles = _read("frontend/src/styles.css")
    combined = "\n".join([api, page, design])

    assert "requestBlob(`/api/data/tables/" in api
    assert "params.set('page'" in api and "params.set('page_size'" in api
    assert "api.databaseTableRows" in page
    assert "api.exportTable" in page
    assert "previewLoading" in design and "previewError" in design
    assert "onPreviewPageChange" in design and "onPreviewRetry" in design
    assert "导出当前范围" in design
    assert "catalog-preview-table" in styles
    assert "FactStatusBar" not in combined
    assert "Math.random" not in combined

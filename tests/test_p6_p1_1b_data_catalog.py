from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.data_access import database_engine
from backend.app.main import app
from backend.app.services.dataset_query_service import DatasetQueryError, export_dataset_csv, query_dataset_rows
from tests.test_p6_p1_1a_data_center import ANALYST, _protected_counts


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_registered_dataset_reads_and_export_remain_read_only():
    engine = database_engine()
    assert engine is not None and engine.dialect.name == "postgresql"
    before = _protected_counts()
    query_dataset_rows("market_price_history", page=1, page_size=5)
    query_dataset_rows("day_ahead_price", page=1, page_size=5)
    export_dataset_csv("forecast_output")
    assert _protected_counts() == before


def test_table_and_view_are_addressed_only_by_dataset_id():
    first = query_dataset_rows("market_price_history", page=1, page_size=5)
    second = query_dataset_rows("market_price_history", page=2, page_size=5)
    view = query_dataset_rows("day_ahead_price", page=1, page_size=5)
    assert first["dataset_id"] == "market_price_history"
    assert first["object_type"] == "table"
    assert first["order_by"] == "observed_at"
    assert first["pagination"]["page"] == 1
    assert second["pagination"]["page"] == 2
    assert view["object_type"] == "view"
    assert all("id" not in row for row in first["records"])


def test_search_is_parameterized_and_unregistered_objects_fail_closed():
    filtered = query_dataset_rows("market_price_history", search="DOM", page_size=3)
    empty = query_dataset_rows("market_price_history", search="%' OR 1=1 --", page_size=3)
    assert filtered["available"] is True and filtered["total"] > 0
    assert empty["available"] is True and empty["total"] == 0
    with pytest.raises(DatasetQueryError) as exc_info:
        query_dataset_rows("users", page_size=3)
    assert exc_info.value.code == "dataset_not_allowed"


def test_dataset_rows_api_has_permission_and_canonical_pagination():
    response = client.get("/api/data/datasets/day_ahead_price/rows?page=2&page_size=4", headers=ANALYST)
    forbidden = client.get(
        "/api/data/datasets/market_price_history/rows?page=1&page_size=4",
        headers={"X-User": "p6_reviewer", "X-Role": "reviewer"},
    )
    assert response.status_code == 200
    assert forbidden.status_code == 403
    payload = response.json()
    assert payload["dataset_id"] == "day_ahead_price"
    assert payload["pagination"]["page"] == 2
    assert payload["pagination"]["page_size"] == 4


def test_export_is_authenticated_memory_csv_and_does_not_create_temp_file():
    export_dir = ROOT / "output" / "exports"
    before = sorted(path.name for path in export_dir.glob("*")) if export_dir.exists() else []
    response = client.get("/api/data/datasets/forecast_output/export", headers=ANALYST)
    after = sorted(path.name for path in export_dir.glob("*")) if export_dir.exists() else []
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert b"run_id" in response.content[:500]
    assert before == after


def test_old_dynamic_browser_routes_are_absent_and_sql_is_gone():
    assert client.get("/api/data/tables", headers=ANALYST).status_code == 404
    assert client.get("/api/data/tables/raw_market/rows", headers=ANALYST).status_code == 404
    blocked = client.post("/api/data/sql/query", headers=ANALYST, json={"sql": "SELECT * FROM users"})
    assert blocked.status_code == 410
    assert blocked.json()["detail"]["code"] == "arbitrary_sql_disabled"


def test_frontend_catalog_preview_uses_dataset_api_and_blob_export():
    api = _read("frontend/src/api.ts")
    page = _read("frontend/src/pages/data/DataCenterPage.tsx")
    design = _read("frontend/src/components/data/DataCenterDesign.tsx")
    combined = "\n".join([api, page, design])
    assert "requestBlob(`/api/data/datasets/" in api
    assert "api.datasetRows" in page
    assert "api.exportDataset" in page
    assert "databaseTableRows" not in combined
    assert "readOnlySql" not in combined
    assert "selected?.dataset_id" in design
    assert "Math.random" not in combined

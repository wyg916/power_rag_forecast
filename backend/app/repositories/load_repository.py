from __future__ import annotations

from typing import Any

from .market_data_repository import load_table_rows, table_exists


def load_forecast_load_from_postgres(limit: int = 5000) -> list[dict[str, Any]]:
    rows = load_table_rows("raw_load", limit=limit, order_by="datetime", where_sql="forecast_load IS NOT NULL")
    if rows:
        return rows
    return load_table_rows("raw_forecast_load_selected", limit=limit, order_by="datetime")


def repository_status() -> dict[str, Any]:
    raw_load_ready = table_exists("raw_load")
    legacy_view_ready = table_exists("raw_forecast_load_selected")
    ready = raw_load_ready or legacy_view_ready
    return {
        "domain": "load",
        "repository": "backend.app.repositories.load_repository",
        "status": "postgresql_ready" if ready else "pending_schema_or_data_migration",
        "tables": [
            {"name": "raw_load", "exists": raw_load_ready},
            {"name": "raw_forecast_load_selected", "exists": legacy_view_ready},
        ],
    }

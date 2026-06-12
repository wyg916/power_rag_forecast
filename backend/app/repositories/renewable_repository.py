from __future__ import annotations

from typing import Any

from .market_data_repository import load_table_rows, table_exists


RENEWABLE_TABLE_CANDIDATES = [
    "raw_renewable",
    "raw_renewable_forecast",
    "raw_solar_forecast",
    "raw_wind_forecast",
]


def load_renewable_forecast_from_postgres(limit: int = 5000) -> list[dict[str, Any]]:
    for table_name in RENEWABLE_TABLE_CANDIDATES:
        rows = load_table_rows(table_name, limit=limit, order_by="datetime")
        if rows:
            return rows
    return []


def repository_status() -> dict[str, Any]:
    table_states = [{"name": table, "exists": table_exists(table)} for table in RENEWABLE_TABLE_CANDIDATES]
    ready = any(item["exists"] for item in table_states)
    return {
        "domain": "renewable",
        "repository": "backend.app.repositories.renewable_repository",
        "status": "postgresql_ready" if ready else "pending_schema_or_data_migration",
        "tables": table_states,
    }

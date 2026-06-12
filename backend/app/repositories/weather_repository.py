from __future__ import annotations

from typing import Any

from .market_data_repository import load_table_rows, table_exists


def load_weather_forecast_from_postgres(limit: int = 5000) -> list[dict[str, Any]]:
    return load_table_rows("raw_weather", limit=limit, order_by="datetime")


def repository_status() -> dict[str, Any]:
    ready = table_exists("raw_weather")
    return {
        "domain": "weather",
        "repository": "backend.app.repositories.weather_repository",
        "status": "postgresql_ready" if ready else "pending_schema_or_data_migration",
        "tables": [{"name": "raw_weather", "exists": ready}],
    }

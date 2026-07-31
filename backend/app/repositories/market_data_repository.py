from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .base import jsonable, mapping_list, postgres_engine


_TABLE_QUERY_POLICIES: dict[str, dict[str, frozenset[str]]] = {
    "raw_market": {
        "order_by": frozenset({"datetime"}),
        "where_sql": frozenset({"", "da_price IS NOT NULL OR price_type = 'DA'"}),
    },
    "raw_da_price": {"order_by": frozenset({"datetime"}), "where_sql": frozenset({""})},
    "raw_weather": {"order_by": frozenset({"datetime"}), "where_sql": frozenset({""})},
    "raw_load": {
        "order_by": frozenset({"datetime"}),
        "where_sql": frozenset({"", "forecast_load IS NOT NULL"}),
    },
    "raw_forecast_load_selected": {"order_by": frozenset({"datetime"}), "where_sql": frozenset({""})},
    "feature_importance": {"order_by": frozenset({"created_at"}), "where_sql": frozenset({""})},
    "model_feature_importance": {"order_by": frozenset({"created_at"}), "where_sql": frozenset({""})},
    "raw_renewable": {"order_by": frozenset({"datetime"}), "where_sql": frozenset({""})},
    "raw_renewable_forecast": {"order_by": frozenset({"datetime"}), "where_sql": frozenset({""})},
    "raw_solar_forecast": {"order_by": frozenset({"datetime"}), "where_sql": frozenset({""})},
    "raw_wind_forecast": {"order_by": frozenset({"datetime"}), "where_sql": frozenset({""})},
}


def table_exists(table_name: str) -> bool:
    if table_name not in _TABLE_QUERY_POLICIES:
        return False
    engine = postgres_engine()
    if engine is None:
        return False
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = current_schema()
                      AND table_name = :table_name
                    LIMIT 1
                    """
                ),
                {"table_name": table_name},
            ).first()
        return row is not None
    except Exception:
        return False


def load_table_rows(table_name: str, limit: int = 5000, order_by: str = "datetime", where_sql: str = "") -> list[dict[str, Any]]:
    policy = _TABLE_QUERY_POLICIES.get(table_name)
    if policy is None:
        return []
    if order_by not in policy["order_by"] or where_sql not in policy["where_sql"]:
        return []
    engine = postgres_engine()
    if engine is None or not table_exists(table_name):
        return []
    safe_limit = max(1, min(int(limit or 5000), 20000))
    safe_where = f" WHERE {where_sql}" if where_sql else ""
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT * FROM {table_name}{safe_where} ORDER BY {order_by} DESC NULLS LAST LIMIT :limit"),
                {"limit": safe_limit},
            ).mappings().all()
        return jsonable(mapping_list(rows))
    except Exception:
        return []


def load_market_history_from_postgres(limit: int = 5000) -> list[dict[str, Any]]:
    rows = load_table_rows("raw_market", limit=limit, order_by="datetime", where_sql="da_price IS NOT NULL OR price_type = 'DA'")
    if rows:
        return rows
    return load_table_rows("raw_da_price", limit=limit, order_by="datetime")


def repository_status() -> dict[str, Any]:
    raw_market_ready = table_exists("raw_market")
    legacy_view_ready = table_exists("raw_da_price")
    ready = raw_market_ready or legacy_view_ready
    return {
        "domain": "market_data",
        "repository": "backend.app.repositories.market_data_repository",
        "status": "postgresql_ready" if ready else "pending_schema_or_data_migration",
        "tables": [
            {"name": "raw_market", "exists": raw_market_ready},
            {"name": "raw_da_price", "exists": legacy_view_ready},
        ],
    }

from __future__ import annotations

from typing import Any

from .market_data_repository import load_table_rows, table_exists


FEATURE_TABLE_CANDIDATES = [
    "feature_importance",
    "model_feature_importance",
]


def load_feature_importance_from_postgres(limit: int = 50) -> list[dict[str, Any]]:
    for table_name in FEATURE_TABLE_CANDIDATES:
        rows = load_table_rows(table_name, limit=limit, order_by="created_at")
        if rows:
            return rows
    return []


def repository_status() -> dict[str, Any]:
    table_states = [{"name": table, "exists": table_exists(table)} for table in FEATURE_TABLE_CANDIDATES]
    ready = any(item["exists"] for item in table_states)
    return {
        "domain": "feature_importance",
        "repository": "backend.app.repositories.feature_repository",
        "status": "postgresql_ready" if ready else "pending_schema_or_data_migration",
        "tables": table_states,
    }

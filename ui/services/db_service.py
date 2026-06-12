from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import text

from automation_common import load_config
from database_utils import (
    create_database_engine,
    ensure_database_structures,
    fetch_ai_report_record,
    fetch_database_overview,
    fetch_recent_run_catalog,
    list_database_browse_sources,
    preview_relation,
    test_database_connection,
)


class DatabaseService:
    def __init__(self):
        self.config = load_config()

    def reload(self) -> None:
        self.config = load_config()

    def test(self) -> tuple[bool, str]:
        self.reload()
        return test_database_connection(self.config)

    def ensure(self) -> None:
        self.reload()
        ensure_database_structures(self.config)

    def overview(self) -> dict[str, Any]:
        self.reload()
        return fetch_database_overview(self.config)

    def run_catalog(self, limit: int = 100) -> pd.DataFrame:
        self.reload()
        return fetch_recent_run_catalog(self.config, limit=limit)

    def sources(self) -> list[dict[str, str]]:
        self.reload()
        return list_database_browse_sources(self.config)

    def preview(self, relation_name: str, limit: int = 200, run_id: str | None = None) -> pd.DataFrame:
        self.reload()
        return preview_relation(self.config, relation_name=relation_name, limit=limit, run_id=run_id)

    def ai_report(self, run_id: str | None = None) -> dict[str, Any] | None:
        self.reload()
        return fetch_ai_report_record(self.config, run_id=run_id)

    def latest_value(self, relation_name: str, column_name: str) -> str:
        self.reload()
        engine = create_database_engine(self.config)
        with engine.connect() as conn:
            value = conn.execute(
                text(f"SELECT MAX(`{column_name}`) FROM `{relation_name}`")
            ).scalar()
        return "" if value is None else str(value)

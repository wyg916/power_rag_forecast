from __future__ import annotations

from functools import lru_cache
from typing import Any
import re

import pandas as pd
from sqlalchemy import inspect, text

from ...config import project_paths
from ...data_access import database_engine, jsonable, read_excel_safe, query_dataframe


DOMAIN_CONFIG = {
    "weather": ("raw_weather", "datetime", "temperature", "weather_raw.xlsx"),
    "da_price": ("raw_da_price", "datetime", "da_price", "da_price_raw.xlsx"),
    "rt_price": ("raw_rt_price", "datetime", "rt_price", "rt_price_raw.xlsx"),
    "load": ("raw_actual_load", "datetime", "actual_load", "actual_load_raw.xlsx"),
    "forecast_load": ("raw_forecast_load_selected", "datetime", "forecast_load", "forecast_load_selected.xlsx"),
    "master_table": ("model_master_table", "datetime", "da_price", "master_table.xlsx"),
}


def _quote(name: str, dialect: str) -> str:
    if dialect == "postgresql":
        return '"' + str(name).replace('"', '""') + '"'
    return "`" + str(name).replace("`", "``") + "`"


def _database_freshness(table: str, dt_col: str, value_col: str) -> pd.DataFrame:
    try:
        engine = database_engine()
        dialect = engine.dialect.name if engine is not None else "mysql"
    except Exception:
        dialect = "mysql"
    q_table = _quote(table, dialect)
    q_dt = _quote(dt_col, dialect)
    q_value = _quote(value_col, dialect)
    return query_dataframe(
        f"""
        SELECT
            MIN({q_dt}) AS min_datetime,
            MAX({q_dt}) AS max_datetime,
            COUNT(*) AS row_count,
            SUM(CASE WHEN {q_dt} IS NULL THEN 1 ELSE 0 END)
              + SUM(CASE WHEN {q_value} IS NULL THEN 1 ELSE 0 END) AS missing_count
        FROM {q_table}
        """
    )


SAFE_TABLE_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _table_columns(table: str) -> list[str]:
    if not SAFE_TABLE_RE.fullmatch(table or ""):
        return []
    engine = database_engine()
    if engine is None:
        return []
    try:
        inspector = inspect(engine)
        names = set(inspector.get_table_names()) | set(inspector.get_view_names())
        if table not in names:
            return []
        return [str(col.get("name")) for col in inspector.get_columns(table)]
    except Exception:
        return []


def _pick_datetime_col(columns: list[str]) -> str | None:
    for name in ["datetime", "forecast_datetime", "predicted_at", "created_at", "updated_at", "generated_at", "date"]:
        if name in columns:
            return name
    for name in columns:
        lower = name.lower()
        if "time" in lower or "date" in lower:
            return name
    return None


def _pick_value_col(table: str, columns: list[str]) -> str | None:
    table_lower = table.lower()
    preferred_by_table = {
        "raw_market": ["lmp", "da_price", "rt_price"],
        "raw_weather": ["temperature", "wind_speed", "humidity"],
        "raw_load": ["forecast_load", "actual_load"],
        "forecast_results": ["predicted_price", "price", "value"],
        "prediction_results": ["predicted_price", "price", "value"],
        "feature_importance": ["importance"],
    }
    for name in preferred_by_table.get(table_lower, []):
        if name in columns:
            return name
    for name in columns:
        lower = name.lower()
        if any(token in lower for token in ["price", "load", "temperature", "value", "importance", "lmp"]):
            return name
    return None


def _safe_quote(name: str, dialect: str) -> str:
    if dialect == "postgresql":
        return '"' + name.replace('"', '""') + '"'
    return "`" + name.replace("`", "``") + "`"


def _database_table_freshness(table: str) -> dict[str, Any]:
    if not SAFE_TABLE_RE.fullmatch(table or ""):
        return {"table": table, "available": False, "message": "表名不合法。"}
    engine = database_engine()
    if engine is None:
        return {"table": table, "available": False, "message": "数据库未启用或连接不可用。"}
    columns = _table_columns(table)
    if not columns:
        return {"table": table, "available": False, "message": "未找到该数据库表或视图。"}
    dt_col = _pick_datetime_col(columns)
    value_col = _pick_value_col(table, columns)
    dialect = engine.dialect.name
    q_table = _safe_quote(table, dialect)
    q_dt = _safe_quote(dt_col, dialect) if dt_col else None
    q_value = _safe_quote(value_col, dialect) if value_col else None
    if q_dt:
        missing_expr = f"SUM(CASE WHEN {q_dt} IS NULL THEN 1 ELSE 0 END)"
        if q_value:
            missing_expr += f" + SUM(CASE WHEN {q_value} IS NULL THEN 1 ELSE 0 END)"
        sql = f"""
        SELECT
            MIN({q_dt}) AS min_datetime,
            MAX({q_dt}) AS max_datetime,
            COUNT(*) AS row_count,
            {missing_expr} AS missing_count
        FROM {q_table}
        """
    else:
        sql = f"SELECT COUNT(*) AS row_count FROM {q_table}"
    try:
        with engine.connect() as conn:
            row = conn.execute(text(sql)).mappings().first() or {}
    except Exception as exc:
        return {"table": table, "available": False, "message": f"读取表失败：{exc}"}
    return {
        "table": table,
        "available": True,
        "datetime_field": dt_col,
        "value_field": value_col,
        "min_datetime": row.get("min_datetime"),
        "max_datetime": row.get("max_datetime"),
        "row_count": int(row.get("row_count") or 0),
        "missing_count": int(row.get("missing_count") or 0),
        "columns": columns[:20],
        "evidence": [{"source": table, "field": dt_col or "", "operation": "min/max/count"}],
    }


def _multi_table_freshness(tables: list[str]) -> dict[str, Any]:
    items = [_database_table_freshness(table) for table in tables]
    return {
        "tool": "get_data_freshness",
        "available": any(item.get("available") for item in items),
        "domain": "database_tables",
        "table": ",".join(tables),
        "multi_table": True,
        "items": items,
        "status": "ok" if all(item.get("available") for item in items) else "partial",
        "evidence": [
            {"source": item.get("table"), "field": item.get("datetime_field") or "", "operation": "min/max/count", "available": item.get("available")}
            for item in items
        ],
    }


@lru_cache(maxsize=16)
def _excel_freshness(file_name: str, dt_col: str, value_col: str) -> dict[str, Any]:
    path = project_paths().data_dir / file_name
    df = read_excel_safe(path)
    if df.empty or dt_col not in df.columns:
        return {}
    datetimes = pd.to_datetime(df[dt_col], errors="coerce")
    missing_count = int(datetimes.isna().sum())
    if value_col in df.columns:
        missing_count += int(pd.to_numeric(df[value_col], errors="coerce").isna().sum())
    return jsonable(
        {
            "min_datetime": datetimes.min(),
            "max_datetime": datetimes.max(),
            "row_count": int(len(df)),
            "missing_count": missing_count,
            "source_file": str(path),
        }
    )


def get_data_freshness(domain: str = "weather", tables: list[str] | None = None, **_: Any) -> dict[str, Any]:
    if tables:
        safe_tables = [str(table).strip().lower() for table in tables if SAFE_TABLE_RE.fullmatch(str(table).strip())]
        if safe_tables:
            return _multi_table_freshness(list(dict.fromkeys(safe_tables))[:8])
    table, dt_col, value_col, file_name = DOMAIN_CONFIG.get(domain, DOMAIN_CONFIG["weather"])
    df = _database_freshness(table, dt_col, value_col)
    source_type = "database"
    if df.empty:
        excel_row = _excel_freshness(file_name, dt_col, value_col)
        if not excel_row:
            return {
                "tool": "get_data_freshness",
                "available": False,
                "domain": domain,
                "table": table,
                "datetime_field": dt_col,
                "value_field": value_col,
                "message": "当前系统未查询到该数据域。",
                "evidence": [{"source": table, "field": dt_col, "operation": "min/max/count", "available": False}],
            }
        row = excel_row
        source_type = "excel_compat"
    else:
        row = df.iloc[0]
    return jsonable(
        {
            "tool": "get_data_freshness",
            "available": True,
            "domain": domain,
            "table": table,
            "source_type": source_type,
            "source_file": row.get("source_file") if isinstance(row, dict) else None,
            "datetime_field": dt_col,
            "value_field": value_col,
            "min_datetime": row.get("min_datetime"),
            "max_datetime": row.get("max_datetime"),
            "row_count": int(row.get("row_count") or 0),
            "missing_count": int(row.get("missing_count") or 0),
            "status": "ok",
            "evidence": [{"source": table, "field": dt_col, "operation": "min/max/count"}],
        }
    )

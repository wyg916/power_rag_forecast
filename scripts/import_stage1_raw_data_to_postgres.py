from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import project_paths
from backend.app.core.config import get_settings


ImportHandler = Callable[[Any, Path, bool, bool, int | None], dict[str, Any]]


def _engine():
    database_url = os.environ.get("DATABASE_URL", "").strip() or get_settings().database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for Stage1 raw data import.")
    return create_engine(database_url, pool_pre_ping=True, future=True)


def _read_table(path: Path, limit: int | None = None) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size <= 0:
        return pd.DataFrame()
    if path.suffix.lower() in {".csv", ".txt"}:
        df = pd.read_csv(path, encoding="utf-8-sig")
    else:
        df = pd.read_excel(path, engine="openpyxl")
    return df.head(limit) if limit else df


def _first_col(df: pd.DataFrame, names: list[str]) -> str | None:
    lower_map = {str(col).strip().lower(): col for col in df.columns}
    for name in names:
        if name.lower() in lower_map:
            return str(lower_map[name.lower()])
    for col in df.columns:
        text_value = str(col).strip().lower()
        if any(name.lower() in text_value for name in names):
            return str(col)
    return None


def _num(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        text_value = str(value).replace(",", "").strip()
        return float(text_value) if text_value else None
    except Exception:
        return None


def _dt(value: Any) -> Any:
    dt = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(dt) else dt.to_pydatetime()


def _json(row: dict[str, Any]) -> str:
    clean: dict[str, Any] = {}
    for key, value in row.items():
        if value is None or pd.isna(value):
            clean[str(key)] = None
        elif hasattr(value, "isoformat"):
            clean[str(key)] = value.isoformat()
        else:
            clean[str(key)] = value
    return json.dumps(clean, ensure_ascii=False, default=str)


def _replace_source(conn, table: str, source_file: str) -> None:
    conn.execute(text(f"DELETE FROM {table} WHERE source_file = :source_file"), {"source_file": source_file})


def _insert_rows(conn, table: str, rows: list[dict[str, Any]], dry_run: bool, replace: bool, source_file: str) -> int:
    if dry_run or not rows:
        return len(rows)
    if replace:
        _replace_source(conn, table, source_file)
    columns = list(rows[0].keys())
    sql = text(
        f"""
        INSERT INTO {table} ({", ".join(columns)})
        VALUES ({", ".join(":" + column for column in columns)})
        """
    )
    conn.execute(sql, rows)
    return len(rows)


def import_market(
    conn,
    path: Path,
    dry_run: bool,
    replace: bool,
    limit: int | None,
    price_type: str = "DA",
) -> dict[str, Any]:
    df = _read_table(path, limit)
    if df.empty:
        return {"table": "raw_market", "source_file": str(path), "rows": 0, "status": "skipped"}

    normalized_type = "RT" if str(price_type).upper() == "RT" else "DA"
    dt_col = _first_col(df, ["datetime", "date_time", "time", "timestamp", "datetime_beginning_ept"])
    price_col = _first_col(
        df,
        ["rt_price", "total_lmp_rt", "lmp", "price"] if normalized_type == "RT" else ["da_price", "total_lmp_da", "lmp", "price"],
    )
    rows = []
    for idx, row in df.iterrows():
        raw = row.to_dict()
        price_value = _num(raw.get(price_col)) if price_col else None
        rows.append(
            {
                "market": str(raw.get("market") or raw.get("pnode_name") or raw.get("node_name") or "DOM"),
                "node_name": str(raw.get("node_name") or raw.get("pnode_name") or raw.get("node") or "DOM"),
                "price_type": normalized_type,
                "datetime": _dt(raw.get(dt_col)) if dt_col else None,
                "da_price": price_value if normalized_type == "DA" else None,
                "rt_price": price_value if normalized_type == "RT" else None,
                "lmp": price_value,
                "source_file": str(path),
                "source_row": int(idx) + 2,
                "raw_json": _json(raw),
            }
        )
    return {
        "table": "raw_market",
        "source_file": str(path),
        "rows": _insert_rows(conn, "raw_market", rows, dry_run, replace, str(path)),
        "status": "ok",
    }


def import_weather(conn, path: Path, dry_run: bool, replace: bool, limit: int | None) -> dict[str, Any]:
    df = _read_table(path, limit)
    if df.empty:
        return {"table": "raw_weather", "source_file": str(path), "rows": 0, "status": "skipped"}
    dt_col = _first_col(df, ["datetime", "date_time", "time", "timestamp"])
    temp_col = _first_col(df, ["temperature", "temp"])
    humidity_col = _first_col(df, ["humidity"])
    wind_col = _first_col(df, ["wind_speed", "wind"])
    rows = []
    for idx, row in df.iterrows():
        raw = row.to_dict()
        rows.append(
            {
                "point_name": str(raw.get("point_name") or raw.get("weather_point_name") or raw.get("city") or ""),
                "city": str(raw.get("city") or ""),
                "datetime": _dt(raw.get(dt_col)) if dt_col else None,
                "temperature": _num(raw.get(temp_col)) if temp_col else None,
                "humidity": _num(raw.get(humidity_col)) if humidity_col else None,
                "wind_speed": _num(raw.get(wind_col)) if wind_col else None,
                "source_file": str(path),
                "source_row": int(idx) + 2,
                "raw_json": _json(raw),
            }
        )
    return {
        "table": "raw_weather",
        "source_file": str(path),
        "rows": _insert_rows(conn, "raw_weather", rows, dry_run, replace, str(path)),
        "status": "ok",
    }


def import_load(
    conn,
    path: Path,
    dry_run: bool,
    replace: bool,
    limit: int | None,
    load_type: str = "forecast",
) -> dict[str, Any]:
    df = _read_table(path, limit)
    if df.empty:
        return {"table": "raw_load", "source_file": str(path), "rows": 0, "status": "skipped"}
    dt_col = _first_col(df, ["datetime", "date_time", "time", "timestamp"])
    forecast_col = _first_col(df, ["forecast_load", "forecast_load_mw", "load"])
    actual_col = _first_col(df, ["actual_load", "mw"])
    normalized_type = "actual" if str(load_type).lower() == "actual" else "forecast"
    rows = []
    for idx, row in df.iterrows():
        raw = row.to_dict()
        actual_value = _num(raw.get(actual_col)) if actual_col else None
        forecast_value = _num(raw.get(forecast_col)) if forecast_col else None
        rows.append(
            {
                "market": str(raw.get("market") or raw.get("load_area") or raw.get("forecast_area") or "DOM"),
                "datetime": _dt(raw.get(dt_col)) if dt_col else None,
                "actual_load": actual_value if normalized_type == "actual" else None,
                "forecast_load": forecast_value if normalized_type == "forecast" else None,
                "source_file": str(path),
                "source_row": int(idx) + 2,
                "raw_json": _json(raw),
            }
        )
    return {
        "table": "raw_load",
        "source_file": str(path),
        "rows": _insert_rows(conn, "raw_load", rows, dry_run, replace, str(path)),
        "status": "ok",
    }


def import_feature_importance(conn, path: Path, dry_run: bool, replace: bool, limit: int | None) -> dict[str, Any]:
    df = _read_table(path, limit)
    if df.empty:
        return {"table": "feature_importance", "source_file": str(path), "rows": 0, "status": "skipped"}
    value_col = _first_col(df, ["importance", "gain", "score"])
    feature_col = next((str(col) for col in df.columns if str(col) != str(value_col)), None)
    rows = []
    for idx, row in df.iterrows():
        raw = row.to_dict()
        rows.append(
            {
                "model_version": str(raw.get("model_version") or "latest"),
                "feature": str(raw.get(feature_col) or ""),
                "importance": _num(raw.get(value_col)) if value_col else None,
                "rank": int(idx) + 1,
                "source_file": str(path),
                "source_row": int(idx) + 2,
                "raw_json": _json(raw),
            }
        )
    return {
        "table": "feature_importance",
        "source_file": str(path),
        "rows": _insert_rows(conn, "feature_importance", rows, dry_run, replace, str(path)),
        "status": "ok",
    }


def _feature_file() -> Path | None:
    result_dir = project_paths().result_table_dir
    for pattern in ["*importance*.xlsx", "13_*.xlsx"]:
        matches = sorted(result_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def _job(name: str, path: Path, handler: ImportHandler) -> tuple[str, Path, ImportHandler]:
    return name, path, handler


def run_import(dry_run: bool = False, replace: bool = False, limit: int | None = None) -> dict[str, Any]:
    paths = project_paths()
    jobs: list[tuple[str, Path, ImportHandler]] = [
        _job("market_da", paths.data_dir / "da_price_raw.xlsx", lambda conn, path, dry_run, replace, limit: import_market(conn, path, dry_run, replace, limit, "DA")),
        _job("market_rt", paths.data_dir / "rt_price_raw.xlsx", lambda conn, path, dry_run, replace, limit: import_market(conn, path, dry_run, replace, limit, "RT")),
        _job("weather", paths.data_dir / "weather_raw.xlsx", import_weather),
        _job("load_actual", paths.data_dir / "actual_load_raw.xlsx", lambda conn, path, dry_run, replace, limit: import_load(conn, path, dry_run, replace, limit, "actual")),
        _job("load_forecast_selected", paths.data_dir / "forecast_load_selected.xlsx", lambda conn, path, dry_run, replace, limit: import_load(conn, path, dry_run, replace, limit, "forecast")),
    ]
    feature_path = _feature_file()
    if feature_path:
        jobs.append(_job("feature_importance", feature_path, import_feature_importance))

    results = []
    engine = _engine()
    with engine.begin() as conn:
        for name, path, handler in jobs:
            try:
                result = handler(conn, path, dry_run, replace, limit)
                result["name"] = name
                results.append(result)
            except Exception as exc:
                results.append({"name": name, "source_file": str(path), "rows": 0, "status": "failed", "error": str(exc)})
    return {
        "status": "ok" if all(item["status"] in {"ok", "skipped"} for item in results) else "partial",
        "dry_run": dry_run,
        "replace": replace,
        "limit": limit,
        "results": results,
        "total_rows": sum(int(item.get("rows") or 0) for item in results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Stage1 raw Excel/CSV files into PostgreSQL raw tables.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    result = run_import(dry_run=args.dry_run, replace=args.replace, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["status"] in {"ok", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

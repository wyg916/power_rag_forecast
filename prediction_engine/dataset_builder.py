from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy import inspect
from sqlalchemy.engine import Engine


TIME_FIELD = "datetime"
TARGET_FIELD = "da_price"
PEAK_HOURS = {6, 7, 8, 9, 10, 11, 18, 19, 20, 21}
MORNING_PEAK_HOURS = {6, 7, 8, 9}
EVENING_PEAK_HOURS = {18, 19, 20, 21}

LEAKAGE_BANNED_FEATURES = {
    TARGET_FIELD,
    "rt_price",
    "lmp",
    "actual_load",
    "price_spread_rt_minus_da",
    "corrected_predicted_price",
    "predicted_price",
    "forecast_datetime",
    "solar_mw",
    "wind_mw",
    "storage_mw",
    "renewable_total_mw",
}


@dataclass(frozen=True)
class DatasetBuilderConfig:
    output_dir: Path = Path("output/p2")
    validation_days: int = 30
    test_days: int = 30
    target_field: str = TARGET_FIELD
    time_field: str = TIME_FIELD
    allow_legacy_fallback: bool = False
    legacy_data_dir: Path | None = None
    output_format: str = "csv"
    max_rows: int | None = None


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def _default_postgres_engine() -> Engine | None:
    try:
        from backend.app.repositories.base import postgres_engine

        return postgres_engine()
    except Exception:
        return None


def _table_exists(engine: Engine, table_name: str) -> bool:
    try:
        return bool(inspect(engine).has_table(table_name))
    except Exception:
        return False


def _table_columns(engine: Engine, table_name: str) -> set[str]:
    try:
        return {str(column["name"]) for column in inspect(engine).get_columns(table_name)}
    except Exception:
        return set()


def _read_sql(engine: Engine, sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql_query(text(sql), conn)


def _aggregate_query(table_name: str, value_columns: list[str]) -> str:
    select_lines = [TIME_FIELD]
    select_lines.extend(f"AVG({column}) AS {column}" for column in value_columns)
    select_lines.append(f"COUNT(*) AS {table_name}_row_count")
    select_sql = ",\n                   ".join(select_lines)
    return f"""
            SELECT {select_sql}
            FROM {table_name}
            WHERE {TIME_FIELD} IS NOT NULL
            GROUP BY {TIME_FIELD}
            ORDER BY {TIME_FIELD}
        """


def read_postgres_source_frames(engine: Engine) -> tuple[dict[str, pd.DataFrame], list[str], dict[str, dict[str, Any]]]:
    """Read P2 source tables through SELECT-only aggregate queries.

    The function accepts any SQLAlchemy engine for tests, but the production
    default resolver only returns PostgreSQL.
    """

    frames: dict[str, pd.DataFrame] = {}
    warnings: list[str] = []
    table_status: dict[str, dict[str, Any]] = {}

    query_specs = {
        "raw_market": ["da_price", "rt_price", "lmp"],
        "raw_load": ["actual_load", "forecast_load"],
        "raw_weather": ["temperature", "humidity", "wind_speed", "precipitation"],
        "raw_renewable": ["solar_mw", "wind_mw", "storage_mw", "renewable_total_mw"],
    }

    for table_name, expected_columns in query_specs.items():
        exists = _table_exists(engine, table_name)
        table_status[table_name] = {"exists": exists, "rows": 0, "used": False, "columns": [], "missing_columns": []}
        if not exists:
            warnings.append(f"{table_name} is not available in the database and was skipped.")
            continue
        actual_columns = _table_columns(engine, table_name)
        if TIME_FIELD not in actual_columns:
            warnings.append(f"{table_name} is missing datetime and was skipped.")
            table_status[table_name]["missing_columns"] = [TIME_FIELD]
            continue
        selected_columns = [column for column in expected_columns if column in actual_columns]
        missing_columns = [column for column in expected_columns if column not in actual_columns]
        if missing_columns:
            warnings.append(f"{table_name} missing columns skipped by dataset builder: {', '.join(missing_columns)}")
        table_status[table_name].update({"columns": selected_columns, "missing_columns": missing_columns})
        sql = _aggregate_query(table_name, selected_columns)
        df = _read_sql(engine, sql)
        table_status[table_name].update({"rows": int(len(df)), "used": True})
        frames[table_name] = df

    for table_name in ["feature_importance", "forecast_results"]:
        exists = _table_exists(engine, table_name)
        table_status[table_name] = {"exists": exists, "rows": None, "used": False}
        if exists:
            try:
                count_df = _read_sql(engine, f"SELECT COUNT(*) AS row_count FROM {table_name}")
                table_status[table_name]["rows"] = int(count_df.iloc[0]["row_count"])
            except Exception as exc:
                warnings.append(f"Failed to count {table_name}: {exc}")

    return frames, warnings, table_status


def read_legacy_master_frame(data_dir: Path) -> tuple[dict[str, pd.DataFrame], list[str], dict[str, dict[str, Any]]]:
    path = data_dir / "master_table.xlsx"
    if not path.exists():
        raise FileNotFoundError(f"legacy fallback requested but master_table.xlsx was not found: {path}")
    df = pd.read_excel(path, engine="openpyxl")
    warnings = [f"Using explicit legacy fallback file: {path}"]
    return {"legacy_master_table": df}, warnings, {"legacy_master_table": {"exists": True, "rows": int(len(df)), "used": True}}


def assemble_training_frame(frames: dict[str, pd.DataFrame], target_field: str = TARGET_FIELD) -> tuple[pd.DataFrame, dict[str, Any]]:
    if "legacy_master_table" in frames:
        base = frames["legacy_master_table"].copy()
    else:
        if "raw_market" not in frames:
            raise ValueError("raw_market is required to build a P2 training dataset.")
        base = frames["raw_market"].copy()
        for name in ["raw_load", "raw_weather", "raw_renewable"]:
            if name in frames:
                base = base.merge(frames[name], on=TIME_FIELD, how="left")

    if TIME_FIELD not in base.columns:
        raise ValueError("training frame is missing datetime.")
    if target_field not in base.columns:
        raise ValueError(f"training frame is missing target field: {target_field}")

    before_rows = len(base)
    base[TIME_FIELD] = pd.to_datetime(base[TIME_FIELD], errors="coerce")
    duplicate_time_count = int(base.duplicated(subset=[TIME_FIELD]).sum())
    base = (
        base.dropna(subset=[TIME_FIELD])
        .sort_values(TIME_FIELD)
        .drop_duplicates(subset=[TIME_FIELD], keep="last")
        .reset_index(drop=True)
    )
    base[target_field] = pd.to_numeric(base[target_field], errors="coerce")
    missing_target_count = int(base[target_field].isna().sum())
    base = base.dropna(subset=[target_field]).reset_index(drop=True)
    diagnostics = {
        "input_rows": int(before_rows),
        "rows_after_datetime_cleaning": int(len(base) + missing_target_count),
        "duplicate_time_count": duplicate_time_count,
        "missing_target_count": missing_target_count,
        "rows_after_target_cleaning": int(len(base)),
    }
    return base, diagnostics


def _safe_shifted_rolling(series: pd.Series, window: int, agg: str) -> pd.Series:
    shifted = pd.to_numeric(series, errors="coerce").shift(1)
    rolling = shifted.rolling(window=window, min_periods=min(max(3, window // 4), window))
    if agg == "mean":
        return rolling.mean()
    if agg == "std":
        return rolling.std()
    if agg == "max":
        return rolling.max()
    if agg == "min":
        return rolling.min()
    raise ValueError(f"unsupported rolling aggregation: {agg}")


def add_p2_safe_features(df: pd.DataFrame, target_field: str = TARGET_FIELD) -> tuple[pd.DataFrame, list[str], list[str]]:
    output = df.copy().sort_values(TIME_FIELD).reset_index(drop=True)
    dt = pd.to_datetime(output[TIME_FIELD], errors="coerce")
    output["hour"] = dt.dt.hour
    output["day_of_week"] = dt.dt.dayofweek
    output["month"] = dt.dt.month
    output["day"] = dt.dt.day
    output["day_of_year"] = dt.dt.dayofyear
    output["week_of_year"] = dt.dt.isocalendar().week.astype("int64")
    output["is_weekend"] = (output["day_of_week"] >= 5).astype(int)
    output["hour_sin"] = np.sin(2 * np.pi * output["hour"] / 24)
    output["hour_cos"] = np.cos(2 * np.pi * output["hour"] / 24)
    output["dow_sin"] = np.sin(2 * np.pi * output["day_of_week"] / 7)
    output["dow_cos"] = np.cos(2 * np.pi * output["day_of_week"] / 7)
    output["month_sin"] = np.sin(2 * np.pi * output["month"] / 12)
    output["month_cos"] = np.cos(2 * np.pi * output["month"] / 12)
    output["is_morning_peak"] = output["hour"].isin(MORNING_PEAK_HOURS).astype(int)
    output["is_evening_peak"] = output["hour"].isin(EVENING_PEAK_HOURS).astype(int)
    output["is_peak_hour"] = output["hour"].isin(PEAK_HOURS).astype(int)

    for lag in [1, 2, 3, 24, 48, 168]:
        output[f"{target_field}_lag_{lag}"] = pd.to_numeric(output[target_field], errors="coerce").shift(lag)

    for col, lags in {
        "forecast_load": [1, 24, 168],
        "actual_load": [1, 24, 168],
        "temperature": [1, 24],
        "humidity": [1, 24],
        "wind_speed": [1, 24],
        "precipitation": [1, 24],
        "rt_price": [24, 168],
        "lmp": [24, 168],
        "renewable_total_mw": [1, 24],
    }.items():
        if col in output.columns:
            for lag in lags:
                output[f"{col}_lag_{lag}"] = pd.to_numeric(output[col], errors="coerce").shift(lag)

    for window in [24, 168]:
        output[f"{target_field}_roll_mean_{window}"] = _safe_shifted_rolling(output[target_field], window, "mean")
        output[f"{target_field}_roll_std_{window}"] = _safe_shifted_rolling(output[target_field], window, "std")
        output[f"{target_field}_roll_max_{window}"] = _safe_shifted_rolling(output[target_field], window, "max")
        if "forecast_load" in output.columns:
            output[f"forecast_load_roll_mean_{window}"] = _safe_shifted_rolling(output["forecast_load"], window, "mean")
            output[f"forecast_load_roll_std_{window}"] = _safe_shifted_rolling(output["forecast_load"], window, "std")
        if "temperature" in output.columns:
            output[f"temperature_roll_mean_{window}"] = _safe_shifted_rolling(output["temperature"], window, "mean")
            output[f"temperature_roll_std_{window}"] = _safe_shifted_rolling(output["temperature"], window, "std")

    if "forecast_load" in output.columns:
        output["forecast_load_x_peak"] = pd.to_numeric(output["forecast_load"], errors="coerce") * output["is_peak_hour"]
    if f"{target_field}_lag_24" in output.columns and f"{target_field}_lag_168" in output.columns:
        output["price_lag_24_vs_168"] = output[f"{target_field}_lag_24"] - output[f"{target_field}_lag_168"]
    if "temperature_lag_1" in output.columns:
        temp = pd.to_numeric(output["temperature"], errors="coerce")
        low = temp.shift(1).rolling(window=24 * 30, min_periods=24 * 7).quantile(0.10)
        high = temp.shift(1).rolling(window=24 * 30, min_periods=24 * 7).quantile(0.90)
        output["is_extreme_weather"] = ((temp <= low) | (temp >= high)).fillna(False).astype(int)
    else:
        output["is_extreme_weather"] = 0

    segment_columns = ["is_peak_hour", "is_morning_peak", "is_evening_peak", "is_extreme_weather"]
    feature_columns = [
        col
        for col in output.columns
        if col not in {TIME_FIELD, target_field}
        and col not in LEAKAGE_BANNED_FEATURES
        and not col.endswith("_row_count")
        and pd.api.types.is_numeric_dtype(output[col])
        and not output[col].isna().all()
    ]
    feature_columns = list(dict.fromkeys(feature_columns))
    return output, feature_columns, segment_columns


def split_by_time(df: pd.DataFrame, config: DatasetBuilderConfig) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    ordered = df.sort_values(config.time_field).reset_index(drop=True)
    if ordered.empty:
        raise ValueError("cannot split an empty dataset.")

    max_dt = ordered[config.time_field].max()
    test_start = max_dt - pd.Timedelta(days=max(1, int(config.test_days)))
    validation_start = test_start - pd.Timedelta(days=max(1, int(config.validation_days)))

    train = ordered[ordered[config.time_field] < validation_start]
    validation = ordered[(ordered[config.time_field] >= validation_start) & (ordered[config.time_field] < test_start)]
    test = ordered[ordered[config.time_field] >= test_start]
    warnings: list[str] = []

    if min(len(train), len(validation), len(test)) == 0:
        warnings.append("Configured day windows produced an empty split; using chronological 70/15/15 fallback.")
        n = len(ordered)
        train_end = max(1, int(n * 0.70))
        validation_end = max(train_end + 1, int(n * 0.85))
        train = ordered.iloc[:train_end]
        validation = ordered.iloc[train_end:validation_end]
        test = ordered.iloc[validation_end:]
        if test.empty and len(validation) > 1:
            test = validation.tail(1)
            validation = validation.iloc[:-1]

    split_info = {
        "method": "chronological_time_split",
        "validation_days": config.validation_days,
        "test_days": config.test_days,
        "warnings": warnings,
        "splits": {
            name: _frame_window(frame, name)
            for name, frame in {"train": train, "validation": validation, "test": test}.items()
        },
        "temporal_order_ok": _temporal_order_ok(train, validation, test, config.time_field),
    }
    return {"train": train.reset_index(drop=True), "validation": validation.reset_index(drop=True), "test": test.reset_index(drop=True)}, split_info


def _frame_window(df: pd.DataFrame, name: str) -> dict[str, Any]:
    if df.empty:
        return {"name": name, "rows": 0, "start_datetime": None, "end_datetime": None}
    return {
        "name": name,
        "rows": int(len(df)),
        "start_datetime": df[TIME_FIELD].min(),
        "end_datetime": df[TIME_FIELD].max(),
    }


def _temporal_order_ok(train: pd.DataFrame, validation: pd.DataFrame, test: pd.DataFrame, time_field: str) -> bool:
    if train.empty or validation.empty or test.empty:
        return False
    return bool(train[time_field].max() < validation[time_field].min() and validation[time_field].max() < test[time_field].min())


def build_feature_schema(
    dataset: pd.DataFrame,
    feature_columns: list[str],
    segment_columns: list[str],
    target_field: str = TARGET_FIELD,
) -> dict[str, Any]:
    features = []
    for column in feature_columns:
        source = "engineered"
        availability = "historical_or_forecast_safe"
        if "_lag_" in column or "_roll_" in column:
            availability = "historical_only_shifted"
        elif column == "forecast_load" or column.startswith("forecast_load_"):
            availability = "forecast_available_at_prediction_time"
            source = "raw_load"
        elif column in {"temperature", "humidity", "wind_speed", "precipitation", "is_extreme_weather"}:
            availability = "requires_weather_forecast_at_prediction_time"
            source = "raw_weather_or_weather_forecast"
        elif column in segment_columns:
            availability = "segment_or_calendar"
        features.append(
            {
                "name": column,
                "dtype": str(dataset[column].dtype),
                "nullable": bool(dataset[column].isna().any()),
                "role": "segment" if column in segment_columns else "feature",
                "source": source,
                "availability": availability,
            }
        )
    schema_payload = {
        "schema_version": "",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "time_field": TIME_FIELD,
        "target": {"name": target_field, "dtype": str(dataset[target_field].dtype), "role": "target"},
        "feature_count": len(feature_columns),
        "features": features,
        "segment_columns": segment_columns,
    }
    signature = json.dumps({"target": target_field, "features": feature_columns}, ensure_ascii=False, sort_keys=True)
    schema_payload["schema_version"] = "p2_features_" + hashlib.sha256(signature.encode("utf-8")).hexdigest()[:12]
    return schema_payload


def validate_feature_schema_consistency(splits: dict[str, pd.DataFrame], feature_columns: list[str]) -> dict[str, Any]:
    expected = list(feature_columns)
    results: dict[str, Any] = {"ok": True, "expected_feature_count": len(expected), "splits": {}}
    expected_set = set(expected)
    for name, frame in splits.items():
        present = [col for col in expected if col in frame.columns]
        missing = sorted(expected_set - set(frame.columns))
        extra = sorted(set(frame.columns) - expected_set - {TIME_FIELD, TARGET_FIELD})
        ok = not missing and present == expected
        results["splits"][name] = {
            "rows": int(len(frame)),
            "ok": ok,
            "missing_features": missing,
            "extra_non_schema_columns": extra[:100],
        }
        results["ok"] = bool(results["ok"] and ok)
    return results


def leakage_check(dataset: pd.DataFrame, feature_columns: list[str], split_info: dict[str, Any]) -> dict[str, Any]:
    banned_present = sorted(col for col in feature_columns if col in LEAKAGE_BANNED_FEATURES)
    risky_patterns = [
        col
        for col in feature_columns
        if (col.startswith("actual_load") and "_lag_" not in col and "_roll_" not in col)
        or (col.startswith("rt_price") and "_lag_" not in col)
        or (col.startswith("lmp") and "_lag_" not in col)
        or col.startswith("corrected_predicted_price")
        or col.startswith("predicted_price")
    ]
    duplicate_time_count = int(dataset.duplicated(subset=[TIME_FIELD]).sum()) if TIME_FIELD in dataset.columns else 0
    return {
        "ok": not banned_present and not risky_patterns and bool(split_info.get("temporal_order_ok")) and duplicate_time_count == 0,
        "banned_present": banned_present,
        "risky_patterns": sorted(set(risky_patterns)),
        "duplicate_time_count": duplicate_time_count,
        "temporal_order_ok": bool(split_info.get("temporal_order_ok")),
        "notes": [
            "All lag and rolling features are shifted before aggregation.",
            "Default split is chronological; random shuffle is not used.",
            "Current actual_load, rt_price, lmp and target da_price are excluded from feature_columns.",
            "Current weather-derived features are allowed only when equivalent weather forecast fields are supplied at prediction time.",
        ],
    }


def _missing_stats(df: pd.DataFrame) -> dict[str, Any]:
    missing = df.isna().sum().sort_values(ascending=False)
    return {
        "columns_with_missing": int((missing > 0).sum()),
        "top_missing": {str(k): int(v) for k, v in missing[missing > 0].head(30).items()},
    }


def write_dataset_outputs(
    output_dir: Path,
    splits: dict[str, pd.DataFrame],
    feature_schema: dict[str, Any],
    summary: dict[str, Any],
    output_format: str = "csv",
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for name, frame in splits.items():
        if output_format == "parquet":
            path = output_dir / f"{name}_dataset.parquet"
            try:
                frame.to_parquet(path, index=False)
            except Exception:
                path = output_dir / f"{name}_dataset.csv"
                frame.to_csv(path, index=False, encoding="utf-8-sig")
        else:
            path = output_dir / f"{name}_dataset.csv"
            frame.to_csv(path, index=False, encoding="utf-8-sig")
        paths[f"{name}_dataset"] = str(path)

    summary_path = output_dir / "dataset_summary.json"
    schema_path = output_dir / "feature_schema.json"
    leakage_path = output_dir / "leakage_check.json"
    _write_json(summary_path, summary)
    _write_json(schema_path, feature_schema)
    _write_json(leakage_path, summary.get("leakage_check", {}))
    paths["dataset_summary"] = str(summary_path)
    paths["feature_schema"] = str(schema_path)
    paths["leakage_check"] = str(leakage_path)
    return paths


def build_p2_datasets(config: DatasetBuilderConfig | None = None, engine: Engine | None = None) -> dict[str, Any]:
    cfg = config or DatasetBuilderConfig()
    warnings: list[str] = []
    source = "postgresql"
    resolved_engine = engine or _default_postgres_engine()
    if resolved_engine is None:
        if not cfg.allow_legacy_fallback:
            raise RuntimeError("PostgreSQL source is unavailable. Set allow_legacy_fallback=True explicitly to use legacy files.")
        data_dir = cfg.legacy_data_dir or Path("output")
        frames, source_warnings, table_status = read_legacy_master_frame(data_dir)
        warnings.extend(source_warnings)
        source = "legacy_file_explicit_fallback"
    else:
        frames, source_warnings, table_status = read_postgres_source_frames(resolved_engine)
        warnings.extend(source_warnings)

    assembled, diagnostics = assemble_training_frame(frames, cfg.target_field)
    if cfg.max_rows:
        assembled = assembled.tail(int(cfg.max_rows)).reset_index(drop=True)
        warnings.append(f"max_rows={cfg.max_rows} applied after source assembly.")
    dataset, feature_columns, segment_columns = add_p2_safe_features(assembled, cfg.target_field)
    splits, split_info = split_by_time(dataset, cfg)
    feature_schema = build_feature_schema(dataset, feature_columns, segment_columns, cfg.target_field)
    schema_check = validate_feature_schema_consistency(splits, feature_columns)
    leak_check = leakage_check(dataset, feature_columns, split_info)

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "config": {**asdict(cfg), "output_dir": str(cfg.output_dir), "legacy_data_dir": str(cfg.legacy_data_dir) if cfg.legacy_data_dir else None},
        "source": source,
        "warnings": warnings,
        "source_tables": table_status,
        "target_field": cfg.target_field,
        "time_field": cfg.time_field,
        "data_start": dataset[cfg.time_field].min(),
        "data_end": dataset[cfg.time_field].max(),
        "sample_count": int(len(dataset)),
        "feature_count": len(feature_columns),
        "feature_columns": feature_columns,
        "segment_columns": segment_columns,
        "assembly_diagnostics": diagnostics,
        "missing_stats": _missing_stats(dataset[[cfg.time_field, cfg.target_field] + feature_columns]),
        "split": split_info,
        "schema_consistency": schema_check,
        "leakage_check": leak_check,
    }
    output_paths = write_dataset_outputs(cfg.output_dir, splits, feature_schema, summary, cfg.output_format)
    summary["output_paths"] = output_paths
    _write_json(Path(output_paths["dataset_summary"]), summary)
    return {"summary": summary, "feature_schema": feature_schema, "splits": splits, "output_paths": output_paths}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build P2 reproducible forecast datasets from PostgreSQL.")
    parser.add_argument("--output-dir", default="output/p2")
    parser.add_argument("--validation-days", type=int, default=30)
    parser.add_argument("--test-days", type=int, default=30)
    parser.add_argument("--allow-legacy-fallback", action="store_true")
    parser.add_argument("--legacy-data-dir", default="")
    parser.add_argument("--output-format", choices=["csv", "parquet"], default="csv")
    parser.add_argument("--max-rows", type=int, default=0)
    args = parser.parse_args()
    config = DatasetBuilderConfig(
        output_dir=Path(args.output_dir),
        validation_days=args.validation_days,
        test_days=args.test_days,
        allow_legacy_fallback=args.allow_legacy_fallback,
        legacy_data_dir=Path(args.legacy_data_dir) if args.legacy_data_dir else None,
        output_format=args.output_format,
        max_rows=args.max_rows or None,
    )
    result = build_p2_datasets(config)
    print(json.dumps({"output_paths": result["output_paths"], "summary": result["summary"]}, ensure_ascii=False, indent=2, default=_json_default))


if __name__ == "__main__":
    main()

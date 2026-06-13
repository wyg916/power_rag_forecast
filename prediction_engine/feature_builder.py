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


TIME_FIELD = "datetime"
TARGET_FIELD = "da_price"
PEAK_HOURS = {6, 7, 8, 9, 10, 11, 18, 19, 20, 21}
MORNING_PEAK_HOURS = {6, 7, 8, 9}
EVENING_PEAK_HOURS = {18, 19, 20, 21}
SAME_HOUR_LAGS = [24, 48, 72, 96, 120, 144, 168]

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
class FeatureBuildConfig:
    target_field: str = TARGET_FIELD
    time_field: str = TIME_FIELD
    mode: str = "training"
    output_dir: Path = Path("output/p2")
    require_weather_forecast_for_current_weather: bool = True


@dataclass(frozen=True)
class FeatureBuildResult:
    frame: pd.DataFrame
    feature_columns: list[str]
    segment_columns: list[str]
    feature_schema: dict[str, Any]
    feature_summary: dict[str, Any]


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


def _add_time_features(output: pd.DataFrame) -> None:
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


def _add_lag_features(output: pd.DataFrame, target_field: str) -> None:
    for lag in [1, 2, 3, *SAME_HOUR_LAGS]:
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


def _add_rolling_features(output: pd.DataFrame, target_field: str) -> None:
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

    same_hour_columns = [f"{target_field}_lag_{lag}" for lag in SAME_HOUR_LAGS if f"{target_field}_lag_{lag}" in output.columns]
    if same_hour_columns:
        output[f"{target_field}_same_hour_7d_mean"] = output[same_hour_columns].mean(axis=1)
        output[f"{target_field}_same_hour_7d_std"] = output[same_hour_columns].std(axis=1)


def _add_interaction_features(output: pd.DataFrame, target_field: str) -> None:
    if "forecast_load" in output.columns:
        output["forecast_load_x_peak"] = pd.to_numeric(output["forecast_load"], errors="coerce") * output["is_peak_hour"]
    if f"{target_field}_lag_24" in output.columns and f"{target_field}_lag_168" in output.columns:
        output["price_lag_24_vs_168"] = output[f"{target_field}_lag_24"] - output[f"{target_field}_lag_168"]
    if "temperature" in output.columns:
        temp = pd.to_numeric(output["temperature"], errors="coerce")
        low = temp.shift(1).rolling(window=24 * 30, min_periods=24 * 7).quantile(0.10)
        high = temp.shift(1).rolling(window=24 * 30, min_periods=24 * 7).quantile(0.90)
        output["is_extreme_weather"] = ((temp <= low) | (temp >= high)).fillna(False).astype(int)
    else:
        output["is_extreme_weather"] = 0


def _feature_metadata(column: str, dataset: pd.DataFrame, segment_columns: list[str]) -> dict[str, Any]:
    source_table = "engineered"
    source_column = ""
    transform = "identity"
    allow_missing_at_prediction = False
    leakage_risk = "low"

    if column in {"hour", "day_of_week", "month", "day", "day_of_year", "week_of_year", "is_weekend"}:
        transform = "calendar_from_datetime"
        allow_missing_at_prediction = False
    elif column in {"hour_sin", "hour_cos", "dow_sin", "dow_cos", "month_sin", "month_cos"}:
        transform = "cyclical_calendar_from_datetime"
    elif column in segment_columns:
        transform = "calendar_or_segment_flag"
    elif column == "forecast_load" or column.startswith("forecast_load_"):
        source_table = "raw_load"
        source_column = "forecast_load"
        transform = "current_forecast_value" if column == "forecast_load" else "shifted_or_rolling_forecast_load"
        allow_missing_at_prediction = False
    elif column in {"temperature", "humidity", "wind_speed", "precipitation"}:
        source_table = "raw_weather_or_weather_forecast"
        source_column = column
        transform = "current_or_forecast_weather_value"
        allow_missing_at_prediction = False
        leakage_risk = "medium_requires_weather_forecast_at_prediction_time"
    elif column.startswith("temperature_") or column.startswith("humidity_") or column.startswith("wind_speed_") or column.startswith("precipitation_"):
        source_table = "raw_weather"
        source_column = column.split("_lag_")[0].split("_roll_")[0]
        transform = "shifted_weather_history"
    elif column.startswith("actual_load_"):
        source_table = "raw_load"
        source_column = "actual_load"
        transform = "shifted_actual_load_history"
    elif column.startswith(f"{TARGET_FIELD}_lag_") or column.startswith(f"{TARGET_FIELD}_roll_") or column.startswith(f"{TARGET_FIELD}_same_hour_"):
        source_table = "raw_market"
        source_column = TARGET_FIELD
        transform = "shifted_target_history"
    elif column.startswith("rt_price_"):
        source_table = "raw_market"
        source_column = "rt_price"
        transform = "shifted_rt_price_history"
    elif column.startswith("lmp_"):
        source_table = "raw_market"
        source_column = "lmp"
        transform = "shifted_lmp_history"
    elif column.startswith("renewable_total_mw_"):
        source_table = "raw_renewable"
        source_column = "renewable_total_mw"
        transform = "shifted_renewable_history"
    elif column == "price_lag_24_vs_168":
        source_table = "raw_market"
        source_column = TARGET_FIELD
        transform = "difference_of_shifted_target_lags"
    elif column == "forecast_load_x_peak":
        source_table = "raw_load"
        source_column = "forecast_load"
        transform = "forecast_load_times_peak_flag"

    return {
        "name": column,
        "dtype": str(dataset[column].dtype),
        "nullable": bool(dataset[column].isna().any()),
        "role": "segment" if column in segment_columns else "feature",
        "source_table": source_table,
        "source_column": source_column,
        "transform": transform,
        "allow_missing_at_prediction": allow_missing_at_prediction,
        "leakage_risk": leakage_risk,
    }


def build_feature_schema(
    dataset: pd.DataFrame,
    feature_columns: list[str],
    segment_columns: list[str],
    target_field: str = TARGET_FIELD,
) -> dict[str, Any]:
    features = [_feature_metadata(column, dataset, segment_columns) for column in feature_columns]
    schema_payload = {
        "schema_version": "",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "time_field": TIME_FIELD,
        "target": {"name": target_field, "dtype": str(dataset[target_field].dtype), "role": "target"},
        "feature_count": len(feature_columns),
        "features": features,
        "segment_columns": segment_columns,
    }
    signature = json.dumps(
        {
            "target": target_field,
            "features": [
                {
                    "name": item["name"],
                    "source_table": item["source_table"],
                    "source_column": item["source_column"],
                    "transform": item["transform"],
                }
                for item in features
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    schema_payload["schema_version"] = "p2_features_" + hashlib.sha256(signature.encode("utf-8")).hexdigest()[:12]
    return schema_payload


def build_feature_summary(
    dataset: pd.DataFrame,
    feature_columns: list[str],
    feature_schema: dict[str, Any],
    config: FeatureBuildConfig,
) -> dict[str, Any]:
    missing = dataset[feature_columns].isna().sum().sort_values(ascending=False) if feature_columns else pd.Series(dtype="int64")
    source_counts: dict[str, int] = {}
    transform_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    for item in feature_schema.get("features", []):
        source_counts[item["source_table"]] = source_counts.get(item["source_table"], 0) + 1
        transform_counts[item["transform"]] = transform_counts.get(item["transform"], 0) + 1
        risk_counts[item["leakage_risk"]] = risk_counts.get(item["leakage_risk"], 0) + 1
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "config": {**asdict(config), "output_dir": str(config.output_dir)},
        "row_count": int(len(dataset)),
        "feature_count": len(feature_columns),
        "feature_columns": feature_columns,
        "source_table_counts": source_counts,
        "transform_counts": transform_counts,
        "leakage_risk_counts": risk_counts,
        "top_missing_features": {str(k): int(v) for k, v in missing[missing > 0].head(30).items()},
        "weather_forecast_required_features": [
            item["name"]
            for item in feature_schema.get("features", [])
            if item["leakage_risk"] == "medium_requires_weather_forecast_at_prediction_time"
        ],
    }


def build_features(frame: pd.DataFrame, config: FeatureBuildConfig | None = None) -> FeatureBuildResult:
    cfg = config or FeatureBuildConfig()
    output = frame.copy().sort_values(cfg.time_field).reset_index(drop=True)
    if cfg.time_field not in output.columns:
        raise ValueError(f"feature frame is missing time field: {cfg.time_field}")
    if cfg.target_field not in output.columns:
        raise ValueError(f"feature frame is missing target field: {cfg.target_field}")

    output[cfg.time_field] = pd.to_datetime(output[cfg.time_field], errors="coerce")
    output = output.dropna(subset=[cfg.time_field]).sort_values(cfg.time_field).reset_index(drop=True)
    _add_time_features(output)
    _add_lag_features(output, cfg.target_field)
    _add_rolling_features(output, cfg.target_field)
    _add_interaction_features(output, cfg.target_field)

    segment_columns = ["is_peak_hour", "is_morning_peak", "is_evening_peak", "is_extreme_weather"]
    feature_columns = [
        col
        for col in output.columns
        if col not in {cfg.time_field, cfg.target_field}
        and col not in LEAKAGE_BANNED_FEATURES
        and not col.endswith("_row_count")
        and pd.api.types.is_numeric_dtype(output[col])
        and not output[col].isna().all()
    ]
    feature_columns = list(dict.fromkeys(feature_columns))
    feature_schema = build_feature_schema(output, feature_columns, segment_columns, cfg.target_field)
    feature_summary = build_feature_summary(output, feature_columns, feature_schema, cfg)
    return FeatureBuildResult(output, feature_columns, segment_columns, feature_schema, feature_summary)


def validate_feature_schema(
    training_schema: dict[str, Any],
    prediction_schema: dict[str, Any],
    model_schema: dict[str, Any] | None = None,
    *,
    strict: bool = True,
) -> dict[str, Any]:
    schemas = {"training": training_schema, "prediction": prediction_schema}
    if model_schema is not None:
        schemas["model"] = model_schema
    names = {name: [item["name"] for item in schema.get("features", [])] for name, schema in schemas.items()}
    reference_name = "training"
    reference = names[reference_name]
    checks: dict[str, Any] = {"ok": True, "strict": strict, "reference": reference_name, "schemas": {}}
    for schema_name, feature_names in names.items():
        missing = [feature for feature in reference if feature not in feature_names]
        extra = [feature for feature in feature_names if feature not in reference]
        order_ok = feature_names == reference
        ok = not missing and (not extra or not strict) and order_ok
        checks["schemas"][schema_name] = {
            "feature_count": len(feature_names),
            "missing_vs_training": missing,
            "extra_vs_training": extra,
            "order_ok": order_ok,
            "ok": ok,
        }
        checks["ok"] = bool(checks["ok"] and ok)
    return checks


def write_feature_outputs(output_dir: Path, feature_schema: dict[str, Any], feature_summary: dict[str, Any]) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    schema_path = output_dir / "feature_schema.json"
    summary_path = output_dir / "feature_summary.json"
    _write_json(schema_path, feature_schema)
    _write_json(summary_path, feature_summary)
    return {"feature_schema": str(schema_path), "feature_summary": str(summary_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build P2 features and feature schema from an assembled CSV.")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-dir", default="output/p2")
    args = parser.parse_args()
    frame = pd.read_csv(args.input_csv)
    result = build_features(frame, FeatureBuildConfig(output_dir=Path(args.output_dir)))
    paths = write_feature_outputs(Path(args.output_dir), result.feature_schema, result.feature_summary)
    print(json.dumps({"output_paths": paths, "feature_summary": result.feature_summary}, ensure_ascii=False, indent=2, default=_json_default))


if __name__ == "__main__":
    main()

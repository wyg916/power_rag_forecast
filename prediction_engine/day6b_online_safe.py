from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


TIME_FIELD = "datetime"
TARGET_FIELD = "da_price"
TRAIN_START = pd.Timestamp("2024-07-13 06:00:00")
TRAIN_END = pd.Timestamp("2026-04-18 23:00:00")
VALIDATION_START = pd.Timestamp("2026-04-19 00:00:00")
VALIDATION_END = pd.Timestamp("2026-05-18 23:00:00")
TEST_START = pd.Timestamp("2026-05-19 00:00:00")
TEST_END = pd.Timestamp("2026-06-17 23:00:00")
PEAK_HOURS = {6, 7, 8, 9, 10, 11, 18, 19, 20, 21}
MORNING_PEAK_HOURS = {6, 7, 8, 9}
EVENING_PEAK_HOURS = {18, 19, 20, 21}


class OnlineSafeContractError(ValueError):
    pass


@dataclass(frozen=True)
class FeatureSpec:
    feature_name: str
    dtype: str
    source_system: str
    availability_latency: str
    max_source_offset_hours: int | None
    derivation: str

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.__dict__,
            "online_available_at_prediction_time": True,
            "leakage_risk": "none_after_anchor_cutoff",
        }


def _calendar_specs() -> list[FeatureSpec]:
    integer = [
        "hour", "day_of_week", "month", "day", "day_of_year", "week_of_year",
        "is_weekend", "is_holiday", "is_morning_peak", "is_evening_peak", "is_peak_hour",
    ]
    cyclic = ["hour_sin", "hour_cos", "dow_sin", "dow_cos", "month_sin", "month_cos"]
    return [
        FeatureSpec(name, "int64", "target_calendar", "0h", None, "deterministic_from_target_datetime")
        for name in integer
    ] + [
        FeatureSpec(name, "float64", "target_calendar", "0h", None, "deterministic_from_target_datetime")
        for name in cyclic
    ]


def feature_specs() -> list[FeatureSpec]:
    specs = _calendar_specs()

    def add_history(
        source: str,
        lags: Iterable[int],
        cutoff: int,
        windows: Iterable[int],
        latency: str,
    ) -> None:
        for lag in lags:
            specs.append(
                FeatureSpec(
                    f"{source}_lag_{lag}", "float64", f"historical_{source}", latency,
                    -int(lag), f"strict_lag_{lag}h_relative_to_target",
                )
            )
        for window in windows:
            for aggregation in ("mean", "std"):
                specs.append(
                    FeatureSpec(
                        f"{source}_anchor_{aggregation}_{window}", "float64",
                        f"historical_{source}", latency, -int(cutoff),
                        f"shift_{cutoff}h_then_trailing_{window}h_{aggregation}",
                    )
                )

    add_history("da_price", (24, 48, 168), 24, (24, 168), "published_day_ahead")
    add_history("actual_load", (25, 48, 168), 25, (24, 168), "1h_reporting_guard")
    for source in ("temperature", "wind_speed", "precipitation"):
        add_history(source, (48, 168), 25, (24, 168), "1h_reporting_guard")
    specs.extend(
        [
            FeatureSpec(
                "da_price_same_hour_mean_7d", "float64", "historical_da_price",
                "published_day_ahead", -24, "previous_7_same_hour_values_ending_target_minus_24h",
            ),
            FeatureSpec(
                "da_price_same_hour_std_7d", "float64", "historical_da_price",
                "published_day_ahead", -24, "previous_7_same_hour_values_ending_target_minus_24h",
            ),
            FeatureSpec(
                "actual_load_same_hour_mean_7d", "float64", "historical_actual_load",
                "1h_reporting_guard", -48, "previous_7_same_hour_values_ending_target_minus_48h",
            ),
        ]
    )
    return specs


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_feature_specs(specs: list[FeatureSpec] | None = None) -> dict[str, Any]:
    values = specs or feature_specs()
    names = [item.feature_name for item in values]
    duplicate_names = sorted({name for name in names if names.count(name) > 1})
    unsafe_offsets = [
        item.feature_name
        for item in values
        if item.max_source_offset_hours is not None and item.max_source_offset_hours > -24
    ]
    banned = [
        name for name in names
        if name in {"da_price", "actual_load", "rt_price", "price_spread_rt_minus_da"}
        or "future_actual" in name or "placeholder" in name
    ]
    result = {
        "ok": not duplicate_names and not unsafe_offsets and not banned and len(values) == 52,
        "feature_count": len(values),
        "duplicate_names": duplicate_names,
        "unsafe_offsets": unsafe_offsets,
        "banned_features": banned,
        "feature_version": "features_online_safe_" + canonical_sha256([item.as_dict() for item in values])[:12],
    }
    if not result["ok"]:
        raise OnlineSafeContractError(f"online-safe feature manifest invalid: {result}")
    return result


def build_online_safe_features(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[FeatureSpec]]:
    required = {
        TIME_FIELD, TARGET_FIELD, "actual_load", "temperature", "wind_speed",
        "precipitation", "is_holiday",
    }
    missing = sorted(required - set(raw.columns))
    if missing:
        raise OnlineSafeContractError(f"training snapshot missing required columns: {missing}")
    frame = raw.copy()
    frame[TIME_FIELD] = pd.to_datetime(frame[TIME_FIELD], errors="raise")
    frame = frame.sort_values(TIME_FIELD).reset_index(drop=True)
    if frame[TIME_FIELD].duplicated().any():
        raise OnlineSafeContractError("training snapshot contains duplicate datetimes")
    if not frame[TIME_FIELD].is_monotonic_increasing:
        raise OnlineSafeContractError("training snapshot is not chronological")
    for column in required - {TIME_FIELD}:
        frame[column] = pd.to_numeric(frame[column], errors="raise")

    dt = frame[TIME_FIELD]
    calendar = {
        "hour": dt.dt.hour,
        "day_of_week": dt.dt.dayofweek,
        "month": dt.dt.month,
        "day": dt.dt.day,
        "day_of_year": dt.dt.dayofyear,
        "week_of_year": dt.dt.isocalendar().week.astype("int64"),
        "is_weekend": (dt.dt.dayofweek >= 5).astype("int64"),
        "is_holiday": frame["is_holiday"].astype("int64"),
        "hour_sin": np.sin(2 * np.pi * dt.dt.hour / 24),
        "hour_cos": np.cos(2 * np.pi * dt.dt.hour / 24),
        "dow_sin": np.sin(2 * np.pi * dt.dt.dayofweek / 7),
        "dow_cos": np.cos(2 * np.pi * dt.dt.dayofweek / 7),
        "month_sin": np.sin(2 * np.pi * dt.dt.month / 12),
        "month_cos": np.cos(2 * np.pi * dt.dt.month / 12),
        "is_morning_peak": dt.dt.hour.isin(MORNING_PEAK_HOURS).astype("int64"),
        "is_evening_peak": dt.dt.hour.isin(EVENING_PEAK_HOURS).astype("int64"),
        "is_peak_hour": dt.dt.hour.isin(PEAK_HOURS).astype("int64"),
    }
    for name, values in calendar.items():
        frame[name] = values

    def history(source: str, lags: Iterable[int], cutoff: int, windows: Iterable[int]) -> None:
        values = frame[source].astype("float64")
        for lag in lags:
            frame[f"{source}_lag_{lag}"] = values.shift(int(lag))
        shifted = values.shift(int(cutoff))
        for window in windows:
            rolling = shifted.rolling(int(window), min_periods=int(window))
            frame[f"{source}_anchor_mean_{window}"] = rolling.mean()
            frame[f"{source}_anchor_std_{window}"] = rolling.std()

    history("da_price", (24, 48, 168), 24, (24, 168))
    history("actual_load", (25, 48, 168), 25, (24, 168))
    for source in ("temperature", "wind_speed", "precipitation"):
        history(source, (48, 168), 25, (24, 168))
    groups = frame.groupby(frame[TIME_FIELD].dt.hour, sort=False)
    frame["da_price_same_hour_mean_7d"] = groups["da_price"].transform(
        lambda values: values.shift(1).rolling(7, min_periods=7).mean()
    )
    frame["da_price_same_hour_std_7d"] = groups["da_price"].transform(
        lambda values: values.shift(1).rolling(7, min_periods=7).std()
    )
    frame["actual_load_same_hour_mean_7d"] = groups["actual_load"].transform(
        lambda values: values.shift(2).rolling(7, min_periods=7).mean()
    )
    specs = feature_specs()
    validate_feature_specs(specs)
    ordered = [item.feature_name for item in specs]
    frame[ordered] = frame[ordered].astype({item.feature_name: item.dtype for item in specs})
    return frame, specs


def split_fixed_windows(frame: pd.DataFrame, feature_names: list[str]) -> dict[str, pd.DataFrame]:
    usable = frame.dropna(subset=feature_names + [TARGET_FIELD]).copy()
    splits = {
        "train": usable[(usable[TIME_FIELD] >= TRAIN_START) & (usable[TIME_FIELD] <= TRAIN_END)],
        "validation": usable[(usable[TIME_FIELD] >= VALIDATION_START) & (usable[TIME_FIELD] <= VALIDATION_END)],
        "test": usable[(usable[TIME_FIELD] >= TEST_START) & (usable[TIME_FIELD] <= TEST_END)],
    }
    expected = {"train": 15472, "validation": 720, "test": 720}
    for name, split in splits.items():
        if len(split) != expected[name]:
            raise OnlineSafeContractError(f"{name} rows={len(split)} expected={expected[name]}")
        if split[feature_names].isna().any().any():
            raise OnlineSafeContractError(f"{name} contains missing candidate features")
    if not (splits["train"][TIME_FIELD].max() < splits["validation"][TIME_FIELD].min() < splits["test"][TIME_FIELD].min()):
        raise OnlineSafeContractError("fixed time windows overlap or are out of order")
    return {name: value.reset_index(drop=True) for name, value in splits.items()}


def _candidate_replacement(name: str) -> str:
    direct = {item.feature_name for item in feature_specs()}
    if name in direct:
        return name
    replacements = {
        "actual_load_lag_1": "actual_load_lag_25",
        "actual_load_lag_2": "actual_load_lag_25",
        "actual_load_hist_change_1h": "actual_load_lag_25",
    }
    if name in replacements:
        return replacements[name]
    for source in ("da_price", "actual_load", "temperature", "wind_speed", "precipitation"):
        for aggregation in ("mean", "std"):
            for window in (24, 168):
                if name in {f"{source}_roll_{aggregation}_{window}", f"{source}_ewm_{aggregation}_{window}"}:
                    return f"{source}_anchor_{aggregation}_{window}"
    return ""


def build_legacy_contract(day6a_matrix: pd.DataFrame) -> pd.DataFrame:
    if len(day6a_matrix) != 170:
        raise OnlineSafeContractError(f"Day 6A matrix must contain 170 rows, got {len(day6a_matrix)}")
    candidate = {item.feature_name: item for item in feature_specs()}
    rows: list[dict[str, Any]] = []
    for record in day6a_matrix.to_dict(orient="records"):
        name = str(record["feature_name"])
        current = str(record["final_decision"])
        availability = str(record.get("availability", ""))
        provider = str(record.get("source_table_or_provider", ""))
        replacement = _candidate_replacement(name)
        if current == "retrain_required":
            if name == "price_spread_rt_minus_da_lag_1" or name in {
                "hour_bias_mean", "scenario_mae", "historical_under_predict_rate",
            }:
                strategy = "remove"
                replacement = ""
            elif name.startswith("actual_load_lag_") or name == "actual_load_hist_change_1h":
                strategy = "lagged_replacement"
            else:
                strategy = "deterministic_online_derivation"
        elif replacement == name:
            strategy = "keep"
        elif replacement:
            strategy = "deterministic_online_derivation"
        else:
            strategy = "remove"

        if current == "block" and "Provider" in provider:
            block_category = "provider_missing"
        elif current == "block" and "historical_lag_if_fresh" in availability:
            block_category = "data_freshness_issue"
        elif current == "block":
            block_category = "model_contract_issue"
        else:
            block_category = "not_applicable"

        spec = candidate.get(replacement)
        if spec and current == "block" and block_category == "data_freshness_issue":
            status = "included_contract_safe_runtime_freshness_blocked"
        elif spec:
            status = "included" if replacement == name else "replaced"
        else:
            status = "excluded"
        rows.append(
            {
                "feature_name": name,
                "dtype": record.get("dtype", "numeric"),
                "current_status": current,
                "online_available_at_prediction_time": "yes" if spec else "no_not_in_candidate",
                "leakage_risk": spec.as_dict()["leakage_risk"] if spec else record.get("leakage_risk", "unknown"),
                "source_system": spec.source_system if spec else provider,
                "availability_latency": spec.availability_latency if spec else availability,
                "replacement_strategy": strategy,
                "candidate_contract_status": status,
                "candidate_feature_name": replacement,
                "block_category": block_category,
                "evidence": (
                    f"Day6A matrix row; candidate derivation={spec.derivation}"
                    if spec else "Day6A matrix row; excluded from online-safe candidate manifest"
                ),
            }
        )
    result = pd.DataFrame(rows)
    counts = result["current_status"].value_counts().to_dict()
    if counts != {"block": 89, "allow": 66, "retrain_required": 15}:
        raise OnlineSafeContractError(f"unexpected Day 6A decision counts: {counts}")
    return result

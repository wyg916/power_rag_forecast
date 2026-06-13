from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from prediction_engine.feature_builder import TARGET_FIELD, TIME_FIELD


HIGH_RISK_COLUMNS = {
    TARGET_FIELD,
    "actual_load",
    "rt_price",
    "lmp",
    "forecast_datetime",
    "predicted_price",
    "corrected_predicted_price",
}


@dataclass(frozen=True)
class LeakageCheckConfig:
    dataset_dir: Path = Path("output/p2")
    output_dir: Path = Path("output/p2")
    target_field: str = TARGET_FIELD
    time_field: str = TIME_FIELD


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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default, allow_nan=False), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_split(dataset_dir: Path, name: str) -> pd.DataFrame:
    csv_path = dataset_dir / f"{name}_dataset.csv"
    parquet_path = dataset_dir / f"{name}_dataset.parquet"
    if csv_path.exists():
        frame = pd.read_csv(csv_path)
    elif parquet_path.exists():
        frame = pd.read_parquet(parquet_path)
    else:
        raise FileNotFoundError(f"dataset split not found: {csv_path} or {parquet_path}")
    if TIME_FIELD in frame.columns:
        frame[TIME_FIELD] = pd.to_datetime(frame[TIME_FIELD], errors="coerce")
    return frame


def load_dataset_splits(dataset_dir: Path) -> dict[str, pd.DataFrame]:
    return {name: _read_split(dataset_dir, name) for name in ["train", "validation", "test"]}


def load_feature_schema(dataset_dir: Path) -> dict[str, Any]:
    path = dataset_dir / "feature_schema.json"
    if not path.exists():
        raise FileNotFoundError(f"feature_schema.json not found: {path}")
    return _read_json(path)


def _issue(code: str, severity: str, message: str, evidence: Any = None) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "evidence": evidence}


def _window(frame: pd.DataFrame, time_field: str) -> dict[str, Any]:
    if frame.empty or time_field not in frame.columns:
        return {"rows": int(len(frame)), "start": None, "end": None}
    return {"rows": int(len(frame)), "start": frame[time_field].min(), "end": frame[time_field].max()}


def _check_time_splits(splits: dict[str, pd.DataFrame], time_field: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    windows = {name: _window(frame, time_field) for name, frame in splits.items()}
    for name, frame in splits.items():
        if time_field not in frame.columns:
            issues.append(_issue("missing_time_field", "high", f"{name} split is missing time field.", {"split": name}))
            continue
        if frame[time_field].isna().any():
            issues.append(_issue("missing_time_values", "medium", f"{name} split contains invalid timestamps.", {"split": name}))
        if not frame[time_field].is_monotonic_increasing:
            issues.append(_issue("split_not_time_sorted", "high", f"{name} split is not sorted by time.", {"split": name}))

    ordered = ["train", "validation", "test"]
    for left, right in zip(ordered, ordered[1:]):
        left_end = windows[left]["end"]
        right_start = windows[right]["start"]
        if left_end is None or right_start is None:
            continue
        if left_end >= right_start:
            issues.append(
                _issue(
                    "train_test_time_overlap",
                    "high",
                    f"{left} and {right} time windows overlap or touch out of order.",
                    {"left": windows[left], "right": windows[right]},
                )
            )

    combined = pd.concat([frame[[time_field]].assign(split=name) for name, frame in splits.items() if time_field in frame.columns], ignore_index=True)
    duplicate_times = combined[combined.duplicated(subset=[time_field], keep=False)]
    if not duplicate_times.empty:
        issues.append(
            _issue(
                "duplicate_time_across_splits",
                "high",
                "The same timestamp appears in more than one split.",
                {"count": int(duplicate_times[time_field].nunique())},
            )
        )
    return issues


def _transform_has_history_guard(transform: str, name: str) -> bool:
    text = f"{name} {transform}".lower()
    if "lag_" in text or "shifted" in text or "rolling" in text or "same_hour" in text:
        return True
    return False


def _check_feature_schema(feature_schema: dict[str, Any], target_field: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for feature in feature_schema.get("features", []):
        name = str(feature.get("name", ""))
        source_table = str(feature.get("source_table", ""))
        source_column = str(feature.get("source_column", ""))
        transform = str(feature.get("transform", ""))
        leakage_risk = str(feature.get("leakage_risk", ""))

        if name == target_field or source_column == target_field and not _transform_has_history_guard(transform, name):
            issues.append(_issue("target_field_leakage", "high", "Target field appears as an unshifted feature.", feature))
        if name in HIGH_RISK_COLUMNS:
            issues.append(_issue("raw_high_risk_feature", "high", f"High risk raw field used as feature: {name}", feature))
        if source_table == "forecast_results":
            issues.append(_issue("forecast_results_feature", "high", "forecast_results must not be used as a training feature.", feature))
        if source_column == "actual_load" and not _transform_has_history_guard(transform, name):
            issues.append(_issue("future_actual_load", "high", "Current/future actual_load is not allowed for future prediction.", feature))
        if source_table == "raw_weather" and transform == "current_or_forecast_weather_value":
            issues.append(_issue("future_true_weather", "high", "Current weather feature is not marked as forecast-provided.", feature))
        if "weather_forecast" in source_table and leakage_risk != "medium_requires_weather_forecast_at_prediction_time":
            issues.append(_issue("weather_forecast_contract_missing", "medium", "Weather forecast feature lacks explicit leakage risk contract.", feature))
        if ("roll" in name or "rolling" in transform) and "shifted" not in transform and "same_hour" not in name:
            issues.append(_issue("rolling_without_shift_contract", "high", "Rolling feature is not marked as shifted/history-only.", feature))
        if "lag" in name and not _transform_has_history_guard(transform, name):
            issues.append(_issue("lag_without_history_contract", "medium", "Lag-like feature lacks shifted transform contract.", feature))
    return issues


def _check_feature_timestamps(splits: dict[str, pd.DataFrame], time_field: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for split_name, frame in splits.items():
        for candidate in ["feature_datetime", "feature_timestamp", "source_datetime"]:
            if candidate in frame.columns and time_field in frame.columns:
                feature_time = pd.to_datetime(frame[candidate], errors="coerce")
                target_time = pd.to_datetime(frame[time_field], errors="coerce")
                late_count = int((feature_time > target_time).sum())
                if late_count:
                    issues.append(
                        _issue(
                            "feature_time_after_target",
                            "high",
                            "Feature timestamp is later than prediction target timestamp.",
                            {"split": split_name, "column": candidate, "count": late_count},
                        )
                    )
    return issues


def check_leakage(
    splits: dict[str, pd.DataFrame],
    feature_schema: dict[str, Any],
    config: LeakageCheckConfig | None = None,
) -> dict[str, Any]:
    cfg = config or LeakageCheckConfig()
    issues: list[dict[str, Any]] = []
    issues.extend(_check_time_splits(splits, cfg.time_field))
    issues.extend(_check_feature_schema(feature_schema, cfg.target_field))
    issues.extend(_check_feature_timestamps(splits, cfg.time_field))

    high = [issue for issue in issues if issue["severity"] == "high"]
    medium = [issue for issue in issues if issue["severity"] == "medium"]
    windows = {name: _window(frame, cfg.time_field) for name, frame in splits.items()}
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "config": {**asdict(cfg), "dataset_dir": str(cfg.dataset_dir), "output_dir": str(cfg.output_dir)},
        "acceptable_for_backtest": len(high) == 0,
        "high_risk_count": len(high),
        "medium_risk_count": len(medium),
        "issue_count": len(issues),
        "issues": issues,
        "checks": {
            "time_split_chronological": not any(issue["code"] in {"split_not_time_sorted", "train_test_time_overlap", "duplicate_time_across_splits"} for issue in issues),
            "random_shuffle_detected": any(issue["code"] == "split_not_time_sorted" for issue in issues),
            "target_not_used_as_feature": not any(issue["code"] == "target_field_leakage" for issue in issues),
            "forecast_results_not_used": not any(issue["code"] == "forecast_results_feature" for issue in issues),
            "feature_time_not_after_target": not any(issue["code"] == "feature_time_after_target" for issue in issues),
        },
        "split_windows": windows,
    }


def _render_report(result: dict[str, Any]) -> str:
    lines = [
        "# P2 Leakage Check Report",
        "",
        f"- created_at: {result['created_at']}",
        f"- acceptable_for_backtest: {result['acceptable_for_backtest']}",
        f"- high_risk_count: {result['high_risk_count']}",
        f"- medium_risk_count: {result['medium_risk_count']}",
        "",
        "## Split Windows",
        "",
    ]
    for name, window in result.get("split_windows", {}).items():
        lines.append(f"- {name}: rows={window['rows']}, start={window['start']}, end={window['end']}")
    lines.extend(["", "## Checks", ""])
    for name, ok in result.get("checks", {}).items():
        lines.append(f"- {name}: {ok}")
    lines.extend(["", "## Issues", ""])
    if not result.get("issues"):
        lines.append("- No leakage issues detected.")
    else:
        for issue in result["issues"]:
            lines.append(f"- [{issue['severity']}] {issue['code']}: {issue['message']}")
    lines.append("")
    return "\n".join(lines)


def run_leakage_check(config: LeakageCheckConfig | None = None) -> dict[str, Any]:
    cfg = config or LeakageCheckConfig()
    splits = load_dataset_splits(cfg.dataset_dir)
    feature_schema = load_feature_schema(cfg.dataset_dir)
    result = check_leakage(splits, feature_schema, cfg)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = cfg.output_dir / "leakage_check_result.json"
    report_path = cfg.output_dir / "leakage_check_report.md"
    _write_json(json_path, result)
    report_path.write_text(_render_report(result), encoding="utf-8")
    result["output_paths"] = {"leakage_check_result": str(json_path), "leakage_check_report": str(report_path)}
    _write_json(json_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run P2 leakage checks against dataset splits and feature schema.")
    parser.add_argument("--dataset-dir", default="output/p2")
    parser.add_argument("--output-dir", default="output/p2")
    args = parser.parse_args()
    result = run_leakage_check(LeakageCheckConfig(dataset_dir=Path(args.dataset_dir), output_dir=Path(args.output_dir)))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default, allow_nan=False))


if __name__ == "__main__":
    main()

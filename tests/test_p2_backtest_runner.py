from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from prediction_engine.backtest_runner import BacktestRunnerConfig, run_backtest
from prediction_engine.feature_builder import SAME_HOUR_LAGS


def _write_split(path: Path, name: str, start: str, periods: int, offset: float) -> None:
    dt = pd.date_range(start, periods=periods, freq="h")
    frame = pd.DataFrame(
        {
            "datetime": dt,
            "da_price": [60.0 + offset + (i % 24) * 2.0 for i in range(periods)],
            "is_peak_hour": [1 if hour in {6, 7, 8, 9, 18, 19, 20} else 0 for hour in dt.hour],
            "is_extreme_weather": [1 if i % 13 == 0 else 0 for i in range(periods)],
        }
    )
    for lag in SAME_HOUR_LAGS:
        frame[f"da_price_lag_{lag}"] = [58.0 + offset + (i % 24) * 1.8 for i in range(periods)]
    frame.loc[frame.index[-5:], "da_price"] += 60.0
    frame.to_csv(path / f"{name}_dataset.csv", index=False, encoding="utf-8-sig")


def _write_schema(path: Path) -> None:
    features = [
        {
            "name": "da_price_lag_24",
            "dtype": "float64",
            "nullable": False,
            "source_table": "raw_market",
            "source_column": "da_price",
            "transform": "shifted_target_history",
            "allow_missing_at_prediction": False,
            "leakage_risk": "low",
        }
    ]
    for lag in [48, 72, 96, 120, 144, 168]:
        features.append({**features[0], "name": f"da_price_lag_{lag}"})
    features.extend(
        [
            {**features[0], "name": "is_peak_hour", "source_table": "engineered", "source_column": "", "transform": "calendar_or_segment_flag"},
            {**features[0], "name": "is_extreme_weather", "source_table": "engineered", "source_column": "", "transform": "calendar_or_segment_flag"},
        ]
    )
    payload = {
        "schema_version": "unit_backtest_schema",
        "time_field": "datetime",
        "target": {"name": "da_price", "dtype": "float64"},
        "feature_count": len(features),
        "features": features,
    }
    (path / "feature_schema.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_dataset_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _write_split(path, "train", "2026-01-01", 240, 0.0)
    _write_split(path, "validation", "2026-01-11", 72, 1.0)
    _write_split(path, "test", "2026-01-14", 72, 2.0)
    _write_schema(path)


def test_backtest_runner_outputs_required_metrics_and_files(tmp_path):
    _write_dataset_dir(tmp_path)

    result = run_backtest(BacktestRunnerConfig(dataset_dir=tmp_path, output_dir=tmp_path, include_legacy=False, spike_quantile=0.80))

    assert Path(result["output_paths"]["metrics"]).exists()
    assert Path(result["output_paths"]["backtest_report"]).exists()
    assert Path(result["output_paths"]["backtest_predictions"]).exists()
    assert result["acceptable_for_backtest"] is True
    assert result["metrics"]

    first = result["metrics"][0]
    assert {"mae", "rmse", "mape", "r2", "sample_count"} <= set(first["overall"])
    assert {"peak_hour_mae", "peak_hour_rmse", "peak_hour_bias", "peak_hour_sample_count"} <= set(first["peak"])
    assert {"spike_threshold", "precision", "recall", "f1", "false_positive_count", "false_negative_count"} <= set(first["spike"])
    assert {"definition", "extreme_weather_mae", "extreme_weather_rmse", "sample_count"} <= set(first["extreme_weather"])
    assert len(first["hourly"]) == 24
    assert result["baseline_comparisons"]


def test_backtest_runner_marks_high_risk_leakage_unacceptable(tmp_path):
    _write_dataset_dir(tmp_path)
    schema = json.loads((tmp_path / "feature_schema.json").read_text(encoding="utf-8"))
    schema["features"].append(
        {
            "name": "da_price",
            "dtype": "float64",
            "nullable": False,
            "source_table": "raw_market",
            "source_column": "da_price",
            "transform": "identity",
            "allow_missing_at_prediction": False,
            "leakage_risk": "high",
        }
    )
    (tmp_path / "feature_schema.json").write_text(json.dumps(schema), encoding="utf-8")

    result = run_backtest(BacktestRunnerConfig(dataset_dir=tmp_path, output_dir=tmp_path, include_legacy=False))

    assert result["acceptable_for_backtest"] is False
    assert result["leakage_check"]["high_risk_count"] > 0

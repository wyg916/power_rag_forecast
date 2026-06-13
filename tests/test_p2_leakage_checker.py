from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from prediction_engine.leakage_checker import LeakageCheckConfig, check_leakage, run_leakage_check


def _split(start: str, periods: int) -> pd.DataFrame:
    dt = pd.date_range(start, periods=periods, freq="h")
    return pd.DataFrame(
        {
            "datetime": dt,
            "da_price": [50.0 + i for i in range(periods)],
            "da_price_lag_24": [49.0 + i for i in range(periods)],
            "is_peak_hour": [1 if hour in {6, 7, 8, 9, 18, 19, 20} else 0 for hour in dt.hour],
            "is_extreme_weather": [0 for _ in range(periods)],
        }
    )


def _schema(features: list[dict]) -> dict:
    return {
        "schema_version": "unit",
        "time_field": "datetime",
        "target": {"name": "da_price"},
        "features": features,
    }


def _safe_feature(name: str = "da_price_lag_24") -> dict:
    return {
        "name": name,
        "dtype": "float64",
        "nullable": False,
        "source_table": "raw_market",
        "source_column": "da_price",
        "transform": "shifted_target_history",
        "allow_missing_at_prediction": False,
        "leakage_risk": "low",
    }


def test_leakage_checker_detects_target_field_leakage():
    splits = {"train": _split("2026-01-01", 48), "validation": _split("2026-01-03", 24), "test": _split("2026-01-04", 24)}
    schema = _schema(
        [
            {
                **_safe_feature("da_price"),
                "source_column": "da_price",
                "transform": "identity",
            }
        ]
    )

    result = check_leakage(splits, schema, LeakageCheckConfig())

    assert result["acceptable_for_backtest"] is False
    assert any(issue["code"] == "target_field_leakage" for issue in result["issues"])


def test_leakage_checker_detects_train_test_time_overlap(tmp_path):
    dataset_dir = tmp_path
    _split("2026-01-01", 48).to_csv(dataset_dir / "train_dataset.csv", index=False)
    _split("2026-01-02", 24).to_csv(dataset_dir / "validation_dataset.csv", index=False)
    _split("2026-01-02 12:00", 24).to_csv(dataset_dir / "test_dataset.csv", index=False)
    (dataset_dir / "feature_schema.json").write_text(json.dumps(_schema([_safe_feature()])), encoding="utf-8")

    result = run_leakage_check(LeakageCheckConfig(dataset_dir=dataset_dir, output_dir=dataset_dir))

    assert Path(result["output_paths"]["leakage_check_result"]).exists()
    assert Path(result["output_paths"]["leakage_check_report"]).exists()
    assert result["acceptable_for_backtest"] is False
    assert any(issue["code"] in {"train_test_time_overlap", "duplicate_time_across_splits"} for issue in result["issues"])

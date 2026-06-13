from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from prediction_engine.baseline_backtest import BaselineBacktestConfig, run_baseline_backtest


def _write_split(path: Path, name: str, start: str, periods: int, offset: float) -> None:
    dt = pd.date_range(start, periods=periods, freq="h")
    frame = pd.DataFrame(
        {
            "datetime": dt,
            "da_price": [50.0 + offset + (i % 24) * 1.5 for i in range(periods)],
            "da_price_lag_24": [49.0 + offset + (i % 24) * 1.5 for i in range(periods)],
            "da_price_lag_168": [48.0 + offset + (i % 24) * 1.3 for i in range(periods)],
            "da_price_roll_mean_24": [49.5 + offset + (i % 12) * 0.8 for i in range(periods)],
            "da_price_roll_mean_168": [48.5 + offset + (i % 12) * 0.6 for i in range(periods)],
            "is_peak_hour": [1 if hour in {6, 7, 8, 9, 10, 18, 19, 20} else 0 for hour in dt.hour],
            "is_extreme_weather": [1 if i % 17 == 0 else 0 for i in range(periods)],
        }
    )
    frame.loc[frame.index[-3:], "da_price"] += 40.0
    frame.to_csv(path / f"{name}_dataset.csv", index=False, encoding="utf-8-sig")


def _write_schema(path: Path, extra_feature: str | None = None) -> None:
    features = [
        "da_price_lag_24",
        "da_price_lag_168",
        "da_price_roll_mean_24",
        "da_price_roll_mean_168",
        "is_peak_hour",
        "is_extreme_weather",
    ]
    if extra_feature:
        features.append(extra_feature)
    payload = {
        "schema_version": "unit_test_schema",
        "time_field": "datetime",
        "target": {"name": "da_price"},
        "features": [{"name": feature, "dtype": "float64", "role": "feature"} for feature in features],
    }
    (path / "feature_schema.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_dataset_dir(path: Path, extra_schema_feature: str | None = None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _write_split(path, "train", "2026-01-01", 240, 0.0)
    _write_split(path, "validation", "2026-01-11", 72, 2.0)
    _write_split(path, "test", "2026-01-14", 72, 4.0)
    _write_schema(path, extra_schema_feature)


def test_run_baseline_backtest_outputs_segment_metrics(tmp_path):
    _write_dataset_dir(tmp_path)

    result = run_baseline_backtest(
        BaselineBacktestConfig(dataset_dir=tmp_path, output_dir=tmp_path, spike_quantile=0.80)
    )

    metrics = result["metrics"]
    summary = result["summary"]

    assert summary["schema_consistency"]["ok"] is True
    assert summary["best_validation_overall"]["split"] == "validation"
    assert Path(result["output_paths"]["baseline_metrics"]).exists()
    assert Path(result["output_paths"]["baseline_backtest_summary"]).exists()

    validation_segments = set(metrics[(metrics["split"] == "validation") & (metrics["baseline"] == "persistence_24h")]["segment"])
    assert {"overall", "peak", "spike", "extreme_weather"} <= validation_segments
    assert not metrics[(metrics["split"] == "test") & (metrics["segment"] == "overall")]["rmse"].isna().all()
    assert summary["spike_detection_metrics"]


def test_run_baseline_backtest_blocks_schema_mismatch(tmp_path):
    _write_dataset_dir(tmp_path, extra_schema_feature="missing_feature")

    with pytest.raises(RuntimeError, match="feature schema mismatch"):
        run_baseline_backtest(BaselineBacktestConfig(dataset_dir=tmp_path, output_dir=tmp_path))

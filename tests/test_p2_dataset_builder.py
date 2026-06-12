from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy import create_engine

from prediction_engine.dataset_builder import (
    DatasetBuilderConfig,
    build_p2_datasets,
)


def _make_source_engine():
    engine = create_engine("sqlite:///:memory:")
    dt = pd.date_range("2026-01-01", periods=240, freq="h")
    raw_market = pd.DataFrame(
        {
            "datetime": dt,
            "da_price": [40.0 + (i % 24) * 0.8 for i in range(len(dt))],
            "rt_price": [41.0 + (i % 24) * 0.7 for i in range(len(dt))],
            "lmp": [39.5 + (i % 24) * 0.6 for i in range(len(dt))],
        }
    )
    raw_load = pd.DataFrame(
        {
            "datetime": dt,
            "actual_load": [1000.0 + (i % 48) * 3.0 for i in range(len(dt))],
            "forecast_load": [990.0 + (i % 48) * 2.5 for i in range(len(dt))],
        }
    )
    raw_weather = pd.DataFrame(
        {
            "datetime": dt,
            "temperature": [15.0 + (i % 24) * 0.5 for i in range(len(dt))],
            "humidity": [55.0 + (i % 10) for i in range(len(dt))],
            "wind_speed": [4.0 + (i % 6) * 0.2 for i in range(len(dt))],
            "precipitation": [0.0 if i % 11 else 1.0 for i in range(len(dt))],
        }
    )
    raw_renewable = pd.DataFrame(
        {
            "datetime": dt,
            "solar_mw": [100.0 + (i % 12) for i in range(len(dt))],
            "wind_mw": [80.0 + (i % 8) for i in range(len(dt))],
            "storage_mw": [20.0 + (i % 4) for i in range(len(dt))],
            "renewable_total_mw": [200.0 + (i % 24) for i in range(len(dt))],
        }
    )
    for name, frame in {
        "raw_market": raw_market,
        "raw_load": raw_load,
        "raw_weather": raw_weather,
        "raw_renewable": raw_renewable,
        "feature_importance": pd.DataFrame({"feature_name": ["hour"], "importance": [1.0]}),
        "forecast_results": pd.DataFrame({"forecast_datetime": dt[:2], "predicted_price": [1.0, 2.0]}),
    }.items():
        frame.to_sql(name, engine, index=False)
    return engine


def test_build_p2_datasets_uses_chronological_splits_and_writes_schema(tmp_path):
    result = build_p2_datasets(
        DatasetBuilderConfig(output_dir=tmp_path, validation_days=2, test_days=2),
        engine=_make_source_engine(),
    )

    summary = result["summary"]
    features = set(summary["feature_columns"])

    assert summary["source"] == "postgresql"
    assert summary["sample_count"] == 240
    assert summary["split"]["method"] == "chronological_time_split"
    assert summary["split"]["temporal_order_ok"] is True
    assert summary["schema_consistency"]["ok"] is True
    assert summary["leakage_check"]["ok"] is True

    assert "da_price" not in features
    assert "actual_load" not in features
    assert "rt_price" not in features
    assert "lmp" not in features
    assert "renewable_total_mw" not in features
    assert {"forecast_load", "actual_load_lag_1", "da_price_lag_24", "is_peak_hour"} <= features

    schema = result["feature_schema"]
    assert schema["schema_version"].startswith("p2_features_")
    assert schema["feature_count"] == len(summary["feature_columns"])
    weather_feature = next(item for item in schema["features"] if item["name"] == "temperature")
    assert weather_feature["availability"] == "requires_weather_forecast_at_prediction_time"

    for key in ["dataset_summary", "feature_schema", "leakage_check", "train_dataset", "validation_dataset", "test_dataset"]:
        assert Path(result["output_paths"][key]).exists()


def test_build_p2_datasets_requires_explicit_legacy_fallback(tmp_path):
    with patch("prediction_engine.dataset_builder._default_postgres_engine", return_value=None):
        with pytest.raises(RuntimeError, match="allow_legacy_fallback=True"):
            build_p2_datasets(DatasetBuilderConfig(output_dir=tmp_path))

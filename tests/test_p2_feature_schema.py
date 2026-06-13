from __future__ import annotations

import pandas as pd

from prediction_engine.feature_builder import FeatureBuildConfig, build_features, validate_feature_schema, write_feature_outputs
from prediction_engine.schema_guard import validate_feature_frame_schema


def _raw_frame(periods: int = 240) -> pd.DataFrame:
    dt = pd.date_range("2026-01-01", periods=periods, freq="h")
    return pd.DataFrame(
        {
            "datetime": dt,
            "da_price": [40.0 + (i % 24) for i in range(periods)],
            "rt_price": [39.0 + (i % 24) for i in range(periods)],
            "lmp": [38.0 + (i % 24) for i in range(periods)],
            "forecast_load": [900.0 + (i % 48) for i in range(periods)],
            "actual_load": [910.0 + (i % 48) for i in range(periods)],
            "temperature": [20.0 + (i % 24) * 0.2 for i in range(periods)],
            "wind_speed": [3.0 + (i % 8) * 0.1 for i in range(periods)],
        }
    )


def test_feature_builder_outputs_required_schema_fields(tmp_path):
    result = build_features(_raw_frame(), FeatureBuildConfig(output_dir=tmp_path))
    paths = write_feature_outputs(tmp_path, result.feature_schema, result.feature_summary)

    assert result.feature_schema["feature_count"] == len(result.feature_columns)
    assert "da_price" not in result.feature_columns
    assert "actual_load" not in result.feature_columns
    assert "rt_price" not in result.feature_columns
    assert "forecast_load" in result.feature_columns
    assert "da_price_same_hour_7d_mean" in result.feature_columns
    assert paths["feature_schema"].endswith("feature_schema.json")
    assert paths["feature_summary"].endswith("feature_summary.json")

    feature = next(item for item in result.feature_schema["features"] if item["name"] == "forecast_load")
    for key in [
        "name",
        "dtype",
        "nullable",
        "source_table",
        "source_column",
        "transform",
        "allow_missing_at_prediction",
        "leakage_risk",
    ]:
        assert key in feature


def test_feature_schema_validation_detects_prediction_missing_field():
    training = build_features(_raw_frame())
    prediction = build_features(_raw_frame())
    prediction_schema = {
        **prediction.feature_schema,
        "features": [item for item in prediction.feature_schema["features"] if item["name"] != "forecast_load"],
    }

    check = validate_feature_schema(training.feature_schema, prediction_schema, training.feature_schema)

    assert check["ok"] is False
    assert "forecast_load" in check["schemas"]["prediction"]["missing_vs_training"]


def test_schema_guard_detects_missing_feature_column():
    built = build_features(_raw_frame())
    frame = built.frame.drop(columns=["forecast_load"])

    check = validate_feature_frame_schema(frame, built.feature_schema)

    assert check["ok"] is False
    assert "forecast_load" in check["missing_features"]

from __future__ import annotations

import pandas as pd
import pytest

from prediction_engine.schema_guard import select_schema_features, validate_feature_frame_schema


def _schema():
    return {
        "schema_version": "unit",
        "features": [
            {"name": "feature_a", "dtype": "float64"},
            {"name": "feature_b", "dtype": "int64"},
        ],
    }


def test_validate_feature_frame_schema_allows_extra_and_selects_ordered_features():
    frame = pd.DataFrame({"feature_b": [1, 2], "extra": ["x", "y"], "feature_a": [1.0, 2.0]})

    check = validate_feature_frame_schema(frame, _schema(), allow_extra=True)
    selected = select_schema_features(frame, _schema())

    assert check["ok"] is True
    assert check["extra_columns"] == ["extra"]
    assert list(selected.columns) == ["feature_a", "feature_b"]


def test_select_schema_features_blocks_missing_feature():
    frame = pd.DataFrame({"feature_a": [1.0, 2.0]})

    check = validate_feature_frame_schema(frame, _schema())

    assert check["ok"] is False
    assert check["missing_features"] == ["feature_b"]
    with pytest.raises(ValueError, match="feature_schema.json"):
        select_schema_features(frame, _schema())


def test_validate_feature_frame_schema_blocks_numeric_dtype_mismatch():
    frame = pd.DataFrame({"feature_a": ["bad"], "feature_b": [1]})

    check = validate_feature_frame_schema(frame, _schema())

    assert check["ok"] is False
    assert check["dtype_mismatches"][0]["name"] == "feature_a"

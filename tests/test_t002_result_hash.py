from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from model_ops.result_hash import (
    RESULT_VALUE_COLUMNS,
    compare_arrays,
    result_data_hash,
    result_manifest_hash,
)


def _frame() -> tuple[pd.DatetimeIndex, pd.DataFrame]:
    timestamps = pd.date_range("2026-06-18", periods=24, freq="h", tz="America/New_York")
    values = pd.DataFrame({name: np.linspace(-1.0, 1.0, 24) for name in RESULT_VALUE_COLUMNS})
    return timestamps, values


def test_result_data_hash_ignores_runtime_metadata_and_column_layout_noise():
    timestamps, values = _frame()
    first = values.copy()
    first["generated_at"] = "2026-07-16T00:00:00Z"
    first["absolute_path"] = "E:/one"
    second = values[list(reversed(values.columns))].copy()
    second["generated_at"] = "2026-07-16T00:01:00Z"
    second["absolute_path"] = "E:/two"
    assert result_data_hash(timestamps, first) == result_data_hash(timestamps, second)


def test_result_data_hash_normalizes_timezone_and_negative_zero():
    timestamps, values = _frame()
    other = values.copy()
    other.loc[0, RESULT_VALUE_COLUMNS[0]] = -0.0
    values.loc[0, RESULT_VALUE_COLUMNS[0]] = 0.0
    assert result_data_hash(timestamps, values) == result_data_hash(timestamps.tz_convert("UTC"), other)


def test_result_data_hash_detects_one_ulp_change():
    timestamps, values = _frame()
    changed = values.copy()
    changed.loc[0, RESULT_VALUE_COLUMNS[-1]] = np.nextafter(changed.loc[0, RESULT_VALUE_COLUMNS[-1]], np.inf)
    assert result_data_hash(timestamps, values) != result_data_hash(timestamps, changed)


def test_result_data_hash_rejects_nan_and_missing_timezone():
    timestamps, values = _frame()
    bad = values.copy()
    bad.loc[0, RESULT_VALUE_COLUMNS[0]] = np.nan
    with pytest.raises(ValueError, match="RESULT_NONFINITE"):
        result_data_hash(timestamps, bad)
    with pytest.raises(ValueError, match="RESULT_TIMEZONE_MISSING"):
        result_data_hash(timestamps.tz_localize(None), values)


def test_result_manifest_hash_ignores_generated_at_and_key_order():
    stable = {
        "artifact_id": "a",
        "model_version": "m",
        "feature_version": "f",
        "schema_hash": "s",
        "input_hash": "i",
        "environment_hash": "e",
        "result_data_hash": "r",
    }
    first = {**stable, "generated_at": "one", "pid": 1, "path": "E:/one"}
    second = {**dict(reversed(list(stable.items()))), "generated_at": "two", "pid": 2, "path": "E:/two"}
    assert result_manifest_hash(first) == result_manifest_hash(second)


def test_compare_arrays_reports_exact_first_difference():
    left = np.array([1.0, 2.0, 3.0])
    right = left.copy()
    right[1] = np.nextafter(right[1], np.inf)
    report = compare_arrays(left, right)
    assert report["equal"] is False
    assert report["numeric_mismatch_count"] == 1
    assert report["bitwise_mismatch_count"] == 1
    assert report["first_mismatch_flat_index"] == 1

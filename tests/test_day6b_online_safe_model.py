from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from backend.app.core.redaction import mask_secret_fields
from prediction_engine.day6b_online_safe import (
    build_legacy_contract,
    build_online_safe_features,
    feature_specs,
    validate_feature_specs,
)


ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "SENTINEL_SECRET_" + "MUST_NOT_LEAK"


def raw_frame(periods: int = 500) -> pd.DataFrame:
    datetimes = pd.date_range("2025-01-01", periods=periods, freq="h")
    index = np.arange(periods, dtype="float64")
    return pd.DataFrame(
        {
            "datetime": datetimes,
            "da_price": 50.0 + np.sin(index / 24.0) * 10.0 + index / 1000.0,
            "actual_load": 1000.0 + np.cos(index / 24.0) * 50.0,
            "temperature": 20.0 + np.sin(index / 168.0) * 8.0,
            "wind_speed": 5.0 + np.cos(index / 72.0),
            "precipitation": (index % 17 == 0).astype("float64"),
            "is_holiday": (datetimes.dayofweek == 6).astype("int64"),
        }
    )


def test_feature_manifest_is_locked_online_safe_and_provider_independent():
    specs = feature_specs()
    result = validate_feature_specs(specs)
    names = [item.feature_name for item in specs]

    assert result["ok"] is True
    assert result["feature_count"] == 52
    assert len(names) == len(set(names))
    assert "forecast_load" not in " ".join(names)
    assert "rt_price" not in " ".join(names)
    assert "price_spread" not in " ".join(names)
    assert min(
        item.max_source_offset_hours
        for item in specs
        if item.max_source_offset_hours is not None and item.source_system == "historical_actual_load"
    ) <= -168
    assert all(
        item.max_source_offset_hours is None or item.max_source_offset_hours <= -24
        for item in specs
    )


def test_feature_builder_is_causal_at_24_hour_anchor():
    original = raw_frame()
    changed = original.copy()
    target_index = 350
    changed.loc[target_index - 23 :, ["da_price", "actual_load", "temperature", "wind_speed", "precipitation"]] += 999999.0

    first, specs = build_online_safe_features(original)
    second, _ = build_online_safe_features(changed)
    names = [item.feature_name for item in specs]

    pd.testing.assert_series_equal(
        first.loc[target_index, names],
        second.loc[target_index, names],
        check_names=False,
    )
    assert first.loc[target_index, "da_price"] != second.loc[target_index, "da_price"]


def test_feature_builder_fails_closed_on_missing_required_source():
    frame = raw_frame().drop(columns=["actual_load"])
    try:
        build_online_safe_features(frame)
    except ValueError as exc:
        assert "actual_load" in str(exc)
    else:
        raise AssertionError("missing actual_load must fail closed")


def test_legacy_contract_covers_170_rows_and_required_dispositions():
    matrix = pd.read_csv(ROOT / "docs/codex/day6a/FEATURE_AVAILABILITY_MATRIX.csv")
    contract = build_legacy_contract(matrix)
    retrain = contract[contract["current_status"] == "retrain_required"]
    blocks = contract[contract["current_status"] == "block"]

    assert len(contract) == 170
    assert contract["feature_name"].is_unique
    assert retrain["replacement_strategy"].value_counts().to_dict() == {
        "deterministic_online_derivation": 8,
        "remove": 4,
        "lagged_replacement": 3,
    }
    assert blocks["block_category"].value_counts().to_dict() == {
        "provider_missing": 56,
        "data_freshness_issue": 33,
    }
    assert not set(retrain["replacement_strategy"]) - {
        "remove", "lagged_replacement", "forecast_replacement",
        "deterministic_online_derivation", "reject",
    }


def test_training_script_cannot_load_active_or_promote_candidate():
    source = (ROOT / "scripts/day6b_train_online_safe_candidate.py").read_text(encoding="utf-8")
    assert "joblib.load" not in source
    assert "promote_to_active" not in source
    assert "activate_model" not in source
    assert "model_registry" not in source
    assert "joblib.dump" in source


def test_sentinel_secret_is_redacted_before_serialization():
    safe = mask_secret_fields({"password": SENTINEL, "nested": {"api_key": SENTINEL}})
    serialized = json.dumps(safe, ensure_ascii=False)
    assert SENTINEL not in serialized
    assert "******" in serialized

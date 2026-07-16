from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_ops.safe_model_contract import (
    PEAK_HOURS,
    ModelContractError,
    _blend_predictions,
    build_artifact_manifest,
    build_feature_contract,
    isolated_load_guards,
    load_verified_candidate,
    prepare_frozen_24_input,
    validate_feature_batch,
    verify_artifact_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "model_artifacts" / "model_20260620_063015"
FIXED_INPUT = ROOT / "结果-3" / "结果表" / "18_未来24小时预测输入特征_正式版.xlsx"


@pytest.fixture(scope="module")
def frozen_batch():
    manifest = build_artifact_manifest(ARTIFACT)
    contract = build_feature_contract(ARTIFACT)
    contract["artifact_id"] = manifest["artifact_id"]
    frame, timestamps = prepare_frozen_24_input(
        FIXED_INPUT,
        FIXED_INPUT,
        contract,
        source_timezone="America/New_York",
    )
    identity = {
        "artifact_id": manifest["artifact_id"],
        "feature_version": manifest["feature_version"],
        "schema_hash": manifest["schema_hash"],
    }
    return manifest, contract, frame, timestamps, identity


def _assert_code(code: str, action) -> None:
    with pytest.raises(ModelContractError) as exc:
        action()
    assert exc.value.code == code


def test_isolated_blend_matches_frozen_legacy_formula():
    base = np.array([-10.0, 20.0, 30.0])
    peak = np.array([-20.0, 50.0, 90.0])
    risk = np.array([0.1, 0.8, 1.2])
    peak_hour = np.array([0, 1, 1])
    load_high = np.array([0, 0, 1])
    error_high = np.array([0, 1, 1])
    predicted, weight = _blend_predictions(
        base,
        peak,
        risk,
        peak_hour,
        alpha=0.1,
        peak_floor=0.0,
        load_high_flag=load_high,
        error_high_flag=error_high,
        spike_threshold=0.8,
    )
    expected_weight = np.array([0.1, 0.48, 0.58])
    np.testing.assert_allclose(weight, expected_weight, rtol=0.0, atol=np.finfo("float64").eps)
    np.testing.assert_allclose(
        predicted,
        base * (1.0 - expected_weight) + peak * expected_weight,
        rtol=0.0,
        atol=np.finfo("float64").eps * 128,
    )
    assert PEAK_HOURS == frozenset({6, 7, 8, 9, 10, 11, 18, 19, 20, 21})


def test_artifact_manifest_identity_and_hashes_are_complete(frozen_batch):
    manifest, contract, frame, timestamps, identity = frozen_batch
    assert manifest["model_version"] == "model_20260620_063015"
    assert manifest["feature_version"] == "features_140db8af25f9"
    assert manifest["feature_count"] == 170
    assert len(manifest["artifact_files"]) == 11
    assert all(len(item["sha256"]) == 64 and item["size_bytes"] > 0 for item in manifest["artifact_files"])
    assert contract["schema_hash"] == manifest["schema_hash"]
    assert manifest["runtime"]["training_runtime_versions"]["detected"]["base_model.joblib"] == "1.6.0"
    assert manifest["model_components"]["p90"] == "lightgbm.sklearn.LGBMRegressor"
    validate_feature_batch(frame, timestamps, contract, identity)


def test_safe_load_rejects_incompatible_sklearn_before_deserialization(frozen_batch, tmp_path: Path):
    manifest, *_ = frozen_batch
    _assert_code(
        "SKLEARN_VERSION_INCOMPATIBLE",
        lambda: load_verified_candidate(ARTIFACT, manifest, authorized_dir=ARTIFACT, output_dir=tmp_path),
    )


def test_manifest_rejects_unauthorized_artifact_path(tmp_path: Path, frozen_batch):
    manifest, *_ = frozen_batch
    _assert_code(
        "ARTIFACT_PATH_UNAUTHORIZED",
        lambda: verify_artifact_manifest(ARTIFACT, manifest, authorized_dir=tmp_path),
    )


def test_manifest_rejects_simulated_artifact_hash_tamper(frozen_batch):
    manifest, *_ = frozen_batch
    tampered = copy.deepcopy(manifest)
    tampered["artifact_hash"] = "0" * 64
    _assert_code(
        "ARTIFACT_HASH_MISMATCH",
        lambda: verify_artifact_manifest(ARTIFACT, tampered, authorized_dir=ARTIFACT),
    )


def test_contract_rejects_missing_feature(frozen_batch):
    _, contract, frame, timestamps, identity = frozen_batch
    _assert_code("MISSING_FEATURE", lambda: validate_feature_batch(frame.drop(columns=[frame.columns[0]]), timestamps, contract, identity))


def test_contract_rejects_extra_feature(frozen_batch):
    _, contract, frame, timestamps, identity = frozen_batch
    bad = frame.copy()
    bad["unexpected"] = 1.0
    _assert_code("EXTRA_FEATURE", lambda: validate_feature_batch(bad, timestamps, contract, identity))


def test_contract_rejects_reordered_features(frozen_batch):
    _, contract, frame, timestamps, identity = frozen_batch
    columns = list(frame.columns)
    columns[0], columns[1] = columns[1], columns[0]
    _assert_code("FEATURE_ORDER_MISMATCH", lambda: validate_feature_batch(frame[columns], timestamps, contract, identity))


def test_contract_rejects_dtype_mismatch(frozen_batch):
    _, contract, frame, timestamps, identity = frozen_batch
    bad = frame.copy()
    bad[bad.columns[0]] = bad[bad.columns[0]].astype("int64")
    _assert_code("DTYPE_MISMATCH", lambda: validate_feature_batch(bad, timestamps, contract, identity))


def test_contract_rejects_illegal_string(frozen_batch):
    _, contract, frame, timestamps, identity = frozen_batch
    bad = frame.copy()
    bad[bad.columns[0]] = bad[bad.columns[0]].astype("object")
    bad.iloc[0, 0] = "invalid"
    _assert_code("ILLEGAL_STRING", lambda: validate_feature_batch(bad, timestamps, contract, identity))


def test_contract_rejects_nan(frozen_batch):
    _, contract, frame, timestamps, identity = frozen_batch
    bad = frame.copy()
    bad.iloc[0, 0] = np.nan
    _assert_code("NAN_FORBIDDEN", lambda: validate_feature_batch(bad, timestamps, contract, identity))


def test_contract_rejects_inf(frozen_batch):
    _, contract, frame, timestamps, identity = frozen_batch
    bad = frame.copy()
    bad.iloc[0, 0] = np.inf
    _assert_code("INF_FORBIDDEN", lambda: validate_feature_batch(bad, timestamps, contract, identity))


def test_contract_rejects_missing_timezone(frozen_batch):
    _, contract, frame, timestamps, identity = frozen_batch
    _assert_code("TIMEZONE_MISSING", lambda: validate_feature_batch(frame, timestamps.tz_localize(None), contract, identity))


def test_contract_rejects_wrong_timezone(frozen_batch):
    _, contract, frame, timestamps, identity = frozen_batch
    _assert_code("TIMEZONE_MISMATCH", lambda: validate_feature_batch(frame, timestamps.tz_convert("UTC"), contract, identity))


@pytest.mark.parametrize("rows", [23, 25])
def test_contract_rejects_non_24_rows(rows: int, frozen_batch):
    _, contract, frame, timestamps, identity = frozen_batch
    if rows == 23:
        bad_frame = frame.iloc[:23].copy()
        bad_times = timestamps[:23]
    else:
        bad_frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
        bad_times = timestamps.append(pd.DatetimeIndex([timestamps[-1] + pd.Timedelta(hours=1)]))
    _assert_code("ROW_COUNT_MISMATCH", lambda: validate_feature_batch(bad_frame, bad_times, contract, identity))


def test_contract_rejects_duplicate_hour(frozen_batch):
    _, contract, frame, timestamps, identity = frozen_batch
    bad = timestamps.to_series(index=range(24))
    bad.iloc[1] = bad.iloc[0]
    _assert_code("DUPLICATE_HOUR", lambda: validate_feature_batch(frame, pd.DatetimeIndex(bad), contract, identity))


def test_contract_rejects_missing_hour(frozen_batch):
    _, contract, frame, timestamps, identity = frozen_batch
    shifted = timestamps[:12].append(timestamps[12:] + pd.Timedelta(hours=1))
    _assert_code("NON_CONTIGUOUS_HOURS", lambda: validate_feature_batch(frame, shifted, contract, identity))


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("feature_version", "wrong", "FEATURE_VERSION_MISMATCH"),
        ("schema_hash", "0" * 64, "SCHEMA_HASH_MISMATCH"),
        ("artifact_id", "wrong", "ARTIFACT_ID_MISMATCH"),
    ],
)
def test_contract_rejects_identity_mismatch(field: str, value: str, code: str, frozen_batch):
    _, contract, frame, timestamps, identity = frozen_batch
    bad_identity = dict(identity)
    bad_identity[field] = value
    _assert_code(code, lambda: validate_feature_batch(frame, timestamps, contract, bad_identity))


def test_contract_rejects_target_column(frozen_batch):
    _, contract, frame, timestamps, identity = frozen_batch
    bad = frame.copy()
    bad["da_price"] = 100.0
    _assert_code("TARGET_COLUMN_FORBIDDEN", lambda: validate_feature_batch(bad, timestamps, contract, identity))


def test_contract_rejects_future_result_column(frozen_batch):
    _, contract, frame, timestamps, identity = frozen_batch
    bad = frame.copy()
    bad["predicted_price"] = 100.0
    _assert_code("FUTURE_RESULT_COLUMN_FORBIDDEN", lambda: validate_feature_batch(bad, timestamps, contract, identity))


def test_contract_rejects_unauthorized_input_path(tmp_path: Path, frozen_batch):
    _, contract, *_ = frozen_batch
    outside = tmp_path / "outside.xlsx"
    outside.write_bytes(b"not-an-excel-file")
    _assert_code(
        "INPUT_PATH_UNAUTHORIZED",
        lambda: prepare_frozen_24_input(outside, FIXED_INPUT, contract, source_timezone="America/New_York"),
    )


def test_contract_rejects_placeholder_drift(frozen_batch):
    _, contract, frame, timestamps, identity = frozen_batch
    bad = frame.copy()
    bad.loc[0, "scenario_mae"] = 1.0
    _assert_code("PLACEHOLDER_VALUE_MISMATCH", lambda: validate_feature_batch(bad, timestamps, contract, identity))


def test_isolated_guards_block_network_subprocess_and_outside_write(tmp_path: Path):
    output = tmp_path / "allowed"
    output.mkdir()
    with isolated_load_guards(output):
        _assert_code("NETWORK_ACCESS_BLOCKED", lambda: __import__("socket").socket())
        _assert_code("SUBPROCESS_BLOCKED", lambda: __import__("subprocess").run(["blocked"]))
        _assert_code("FILE_WRITE_BLOCKED", lambda: (tmp_path / "outside.txt").write_text("blocked", encoding="utf-8"))

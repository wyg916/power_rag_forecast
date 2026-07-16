from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm
import numpy as np
import pandas as pd
import scipy
import sklearn
import threadpoolctl
from lightgbm import LGBMRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestClassifier
from sklearn.exceptions import InconsistentVersionWarning
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline

from model_ops.result_hash import RESULT_VALUE_COLUMNS, result_data_hash, result_manifest_hash
from model_ops.safe_model_contract import (
    PLACEHOLDER_FEATURES,
    _blend_predictions,
    build_artifact_manifest,
    build_feature_contract,
    candidate_identity,
    frame_hash,
    isolated_load_guards,
    load_verified_candidate,
    predict_candidate_components,
    sha256_file,
    validate_feature_batch,
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--sandbox", required=True)
    parser.add_argument("--requirements", required=True)
    return parser.parse_args()


def _environment_hash(requirements: Path) -> tuple[str, str]:
    freeze = subprocess.check_output(
        [str(Path(__file__).resolve().parents[1] / ".codex_envs" / "t002_sklearn160" / "Scripts" / "python.exe"), "-m", "pip", "freeze"],
        text=True,
        encoding="utf-8",
    )
    payload = {
        "python": platform.python_version(),
        "freeze": sorted(line.strip() for line in freeze.splitlines() if line.strip()),
        "requirements_sha256": sha256_file(requirements),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), freeze


def _load_fixed_input(path: Path, contract: dict) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    raw = pd.read_csv(path, encoding="utf-8-sig")
    expected = [item["name"] for item in contract["features"]]
    if list(raw.columns) != ["timestamp", *expected]:
        raise RuntimeError("FROZEN_INPUT_COLUMNS_MISMATCH")
    frame = raw[expected]
    if any(str(dtype) != "float64" for dtype in frame.dtypes):
        raise RuntimeError("FROZEN_INPUT_DTYPE_MISMATCH")
    timestamps = pd.DatetimeIndex(pd.to_datetime(raw["timestamp"], utc=True)).tz_convert(contract["timezone"])
    return frame, timestamps


def _component_details(candidate, feature_names: list[str]) -> dict:
    details = dict(candidate.metadata["interfaces"])
    p90 = candidate.models["p90_model.joblib"]
    booster = p90.booster_
    details["p90_model.joblib"]["lightgbm_version"] = lightgbm.__version__
    details["p90_model.joblib"]["booster_feature_names"] = list(booster.feature_name())
    details["p90_model.joblib"]["booster_num_feature"] = int(booster.num_feature())
    details["p90_model.joblib"]["booster_params"] = dict(booster.params)

    indices = {name: feature_names.index(name) for name in PLACEHOLDER_FEATURES}
    base = candidate.models["base_model.joblib"].steps[-1][1]
    base_coef = np.asarray(base.coef_, dtype="float64").reshape(-1)
    classifier = candidate.models["spike_classifier.joblib"]
    rf_importance = np.asarray(classifier.feature_importances_, dtype="float64")
    lgb_importance = np.asarray(booster.feature_importance(importance_type="gain"), dtype="float64")
    details["placeholder_model_parameters"] = {
        name: {
            "ridge_coefficient": float(base_coef[index]),
            "rf_feature_importance": float(rf_importance[index]),
            "lightgbm_gain_importance": float(lgb_importance[index]),
        }
        for name, index in indices.items()
    }
    return details


def main() -> int:
    args = _args()
    artifact = Path(args.artifact).resolve(strict=True)
    input_path = Path(args.input).resolve(strict=True)
    sandbox = Path(args.sandbox).resolve(strict=True)
    requirements = Path(args.requirements).resolve(strict=True)

    manifest_before = build_artifact_manifest(artifact)
    contract = build_feature_contract(artifact)
    contract["artifact_id"] = manifest_before["artifact_id"]
    frame, timestamps = _load_fixed_input(input_path, contract)
    identity = {
        "artifact_id": manifest_before["artifact_id"],
        "feature_version": manifest_before["feature_version"],
        "schema_hash": manifest_before["schema_hash"],
    }
    validate_feature_batch(frame, timestamps, contract, identity)
    environment_hash, freeze = _environment_hash(requirements)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with isolated_load_guards(sandbox) as runtime_events:
            candidate = load_verified_candidate(
                artifact,
                manifest_before,
                authorized_dir=artifact,
                output_dir=sandbox,
            )
            run1 = predict_candidate_components(candidate, frame, timestamps, candidate_identity(candidate))
            run2 = predict_candidate_components(candidate, frame, timestamps, candidate_identity(candidate))

    warning_records = [{"category": item.category.__name__, "message": str(item.message)} for item in caught]
    if any(issubclass(item.category, InconsistentVersionWarning) for item in caught):
        raise RuntimeError("INCONSISTENT_VERSION_WARNING")

    numeric_columns = list(RESULT_VALUE_COLUMNS)
    numeric_equal = bool(np.array_equal(run1[numeric_columns].to_numpy(), run2[numeric_columns].to_numpy()))
    result_hash_1 = result_data_hash(timestamps, run1)
    result_hash_2 = result_data_hash(timestamps, run2)
    if len(run1) != 24 or len(run2) != 24:
        raise RuntimeError("OUTPUT_ROW_COUNT_MISMATCH")

    negative_probe, _ = _blend_predictions(
        np.array([-10.0]),
        np.array([-20.0]),
        np.array([0.0]),
        np.array([0.0]),
        alpha=0.1,
        peak_floor=0.0,
        load_high_flag=np.array([0.0]),
        error_high_flag=np.array([0.0]),
        spike_threshold=0.8,
    )
    if not float(negative_probe[0]) < 0.0:
        raise RuntimeError("NEGATIVE_PRICE_WAS_CLIPPED")

    generated_1 = datetime.now(timezone.utc).isoformat()
    generated_2 = datetime.now(timezone.utc).isoformat()
    common = {
        "artifact_id": manifest_before["artifact_id"],
        "model_version": manifest_before["model_version"],
        "feature_version": manifest_before["feature_version"],
        "schema_hash": manifest_before["schema_hash"],
        "input_hash": frame_hash(frame),
        "environment_hash": environment_hash,
    }
    manifest_hash_1 = result_manifest_hash({**common, "result_data_hash": result_hash_1})
    manifest_hash_2 = result_manifest_hash({**common, "result_data_hash": result_hash_2})
    for output, generated_at, result_hash, manifest_hash, filename in (
        (run1, generated_1, result_hash_1, manifest_hash_1, "fixed_24_prediction_run1.csv"),
        (run2, generated_2, result_hash_2, manifest_hash_2, "fixed_24_prediction_run2.csv"),
    ):
        export = output.copy()
        for position, (name, value) in enumerate(common.items(), start=1):
            export.insert(position, name, value)
        export.insert(1 + len(common), "generated_at", generated_at)
        export.insert(2 + len(common), "result_data_hash", result_hash)
        export.insert(3 + len(common), "result_manifest_hash", manifest_hash)
        export.to_csv(sandbox / filename, index=False, encoding="utf-8-sig")

    if not numeric_equal or result_hash_1 != result_hash_2:
        raise RuntimeError("DETERMINISM_MISMATCH")

    manifest_after = build_artifact_manifest(artifact)
    if manifest_before["artifact_hash"] != manifest_after["artifact_hash"]:
        raise RuntimeError("ARTIFACT_HASH_CHANGED")

    feature_names = [item["name"] for item in contract["features"]]
    report = {
        "status": "PASS",
        "manifest_before": manifest_before,
        "manifest_after": manifest_after,
        "artifact_hash_equal": True,
        "input_path": str(input_path),
        "input_file_sha256": sha256_file(input_path),
        "input_rows": len(frame),
        "input_features": len(feature_names),
        "input_hash": frame_hash(frame),
        "timezone": str(timestamps.tz),
        "placeholder_values": {name: sorted(map(float, frame[name].unique())) for name in PLACEHOLDER_FEATURES},
        "components": _component_details(candidate, feature_names),
        "warnings": warning_records,
        "inconsistent_version_warning": False,
        "runtime_guard_events": runtime_events,
        "load_guard_events": candidate.guard_events,
        "run1_rows": len(run1),
        "run2_rows": len(run2),
        "run1_all_finite": bool(np.isfinite(run1[numeric_columns].to_numpy()).all()),
        "run2_all_finite": bool(np.isfinite(run2[numeric_columns].to_numpy()).all()),
        "numeric_array_equal": numeric_equal,
        "result_hash_run1": result_hash_1,
        "result_hash_run2": result_hash_2,
        "result_manifest_hash_run1": manifest_hash_1,
        "result_manifest_hash_run2": manifest_hash_2,
        "negative_price_preserved": True,
        "negative_prediction_count_run1": int((run1["predicted_price"] < 0).sum()),
        "environment_hash": environment_hash,
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
            "lightgbm": lightgbm.__version__,
            "threadpoolctl": threadpoolctl.__version__,
        },
        "pip_freeze": freeze.splitlines(),
        "database_access": False,
        "formal_prediction_execution": False,
        "candidate_status_after": "candidate",
        "active_promotion": False,
    }
    (sandbox / "isolated_inference_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: report[key] for key in (
        "status", "artifact_hash_equal", "run1_rows", "run2_rows", "result_hash_run1",
        "result_hash_run2", "numeric_array_equal", "inconsistent_version_warning",
        "negative_price_preserved", "environment_hash"
    )}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

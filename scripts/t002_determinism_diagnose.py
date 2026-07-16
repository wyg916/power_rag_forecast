from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import subprocess
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import lightgbm
import numpy as np
import pandas as pd
import scipy
import sklearn
import threadpoolctl
from sklearn.exceptions import InconsistentVersionWarning

from model_ops.result_hash import (
    RESULT_VALUE_COLUMNS,
    compare_arrays,
    result_data_hash,
    result_manifest_hash,
)
from model_ops.safe_model_contract import (
    PEAK_HOURS,
    PLACEHOLDER_FEATURES,
    _blend_predictions,
    build_artifact_manifest,
    build_feature_contract,
    candidate_identity,
    frame_hash,
    isolated_load_guards,
    load_verified_candidate,
    sha256_file,
    validate_feature_batch,
)


THREAD_ENVIRONMENT = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "PYTHONHASHSEED",
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--requirements", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--rf-mode", choices=("model", "single"), default="model")
    return parser.parse_args()


def _environment_hash(python: Path, requirements: Path) -> tuple[str, list[str]]:
    freeze_text = subprocess.check_output(
        [str(python), "-m", "pip", "freeze"],
        text=True,
        encoding="utf-8",
        env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1"},
    )
    freeze = sorted(line.strip() for line in freeze_text.splitlines() if line.strip())
    payload = {
        "python": platform.python_version(),
        "freeze": freeze,
        "requirements_sha256": sha256_file(requirements),
        "thread_environment": {name: os.environ.get(name) for name in THREAD_ENVIRONMENT},
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), freeze


def _load_fixed_input(path: Path, contract: dict[str, Any]) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    raw = pd.read_csv(path, encoding="utf-8-sig")
    expected = [item["name"] for item in contract["features"]]
    if list(raw.columns) != ["timestamp", *expected]:
        raise RuntimeError("FROZEN_INPUT_COLUMNS_MISMATCH")
    frame = raw[expected]
    if any(str(dtype) != "float64" for dtype in frame.dtypes):
        raise RuntimeError("FROZEN_INPUT_DTYPE_MISMATCH")
    timestamps = pd.DatetimeIndex(pd.to_datetime(raw["timestamp"], utc=True)).tz_convert(contract["timezone"])
    return frame, timestamps


def _predict_components(candidate: Any, frame: pd.DataFrame, timestamps: pd.DatetimeIndex, rf_mode: str) -> pd.DataFrame:
    validate_feature_batch(frame, timestamps, candidate.feature_contract, candidate_identity(candidate))
    base = np.asarray(candidate.models["base_model.joblib"].predict(frame), dtype="float64")
    peak = np.asarray(candidate.models["peak_model.joblib"].predict(frame), dtype="float64")
    classifier = candidate.models["spike_classifier.joblib"]
    if rf_mode == "single":
        classifier = copy.copy(classifier)
        classifier.n_jobs = 1
    classification = np.asarray(classifier.predict(frame), dtype="float64")
    probability = np.asarray(classifier.predict_proba(frame), dtype="float64")[:, 1]
    p90 = np.asarray(candidate.models["p90_model.joblib"].predict(frame, num_threads=1), dtype="float64")
    peak_flags = frame["hour"].isin(PEAK_HOURS).astype(int).to_numpy()
    load_high = (frame["forecast_load"] >= frame["forecast_load"].quantile(0.75)).to_numpy()
    error_high = (frame["scenario_mae"] >= frame["scenario_mae"].quantile(0.75)).to_numpy()
    thresholds = candidate.metadata["thresholds"]
    metrics = candidate.metadata["metrics"]
    training = candidate.metadata["training_config"]
    predicted, weight = _blend_predictions(
        base,
        peak,
        probability,
        peak_flags,
        alpha=thresholds.get("best_alpha", metrics.get("best_alpha", 0.0)),
        peak_floor=thresholds.get("best_peak_floor", metrics.get("best_peak_floor", 0.0)),
        load_high_flag=load_high,
        error_high_flag=error_high,
        spike_threshold=thresholds.get(
            "best_spike_threshold",
            metrics.get("best_spike_threshold", training.get("best_spike_threshold", 0.5)),
        ),
    )
    values = pd.DataFrame(
        {
            "base_prediction": base,
            "peak_prediction": peak,
            "classifier_prediction": classification,
            "spike_probability": probability,
            "p90_prediction": p90,
            "blend_weight": np.asarray(weight, dtype="float64"),
            "predicted_price": np.asarray(predicted, dtype="float64"),
        }
    )
    if len(values) != 24 or values.shape[1] != len(RESULT_VALUE_COLUMNS):
        raise RuntimeError("OUTPUT_SHAPE_MISMATCH")
    if not np.isfinite(values.to_numpy(dtype="float64")).all():
        raise RuntimeError("OUTPUT_NONFINITE")
    return pd.DataFrame({"timestamp": timestamps.astype(str), **{name: values[name] for name in values}})


def _lightgbm_report(candidate: Any, feature_names: list[str], output_shape: list[int]) -> dict[str, Any]:
    wrapper = candidate.models["p90_model.joblib"]
    booster = getattr(wrapper, "booster_", None)
    if booster is None:
        raise RuntimeError("LIGHTGBM_BOOSTER_MISSING")
    names = list(booster.feature_name())
    params = dict(booster.params)
    return {
        "wrapper_module": wrapper.__class__.__module__,
        "wrapper_class": wrapper.__class__.__name__,
        "lightgbm_runtime_version": lightgbm.__version__,
        "training_lightgbm_version": "unknown",
        "validated_inference_lightgbm_version": lightgbm.__version__,
        "booster_present": True,
        "booster_num_feature": int(booster.num_feature()),
        "booster_feature_names": names,
        "booster_params": params,
        "objective": params.get("objective"),
        "num_class": params.get("num_class", 1),
        "num_trees": int(booster.num_trees()),
        "best_iteration": int(wrapper.best_iteration_) if getattr(wrapper, "best_iteration_", None) is not None else None,
        "current_iteration": int(booster.current_iteration()),
        "n_features_in": int(wrapper.n_features_in_),
        "feature_names_in_present": getattr(wrapper, "feature_names_in_", None) is not None,
        "feature_names_match_contract": names == feature_names,
        "input_contract_feature_count": len(feature_names),
        "predict_output_shape": output_shape,
        "prediction_num_threads": 1,
    }


def main() -> int:
    args = _args()
    if args.runs not in (1, 2):
        raise RuntimeError("RUN_COUNT_MUST_BE_ONE_OR_TWO")
    artifact = Path(args.artifact).resolve(strict=True)
    input_path = Path(args.input).resolve(strict=True)
    output = Path(args.output).resolve(strict=True)
    requirements = Path(args.requirements).resolve(strict=True)
    python = Path(args.python).resolve(strict=True)
    manifest_before = build_artifact_manifest(artifact)
    contract = build_feature_contract(artifact)
    contract["artifact_id"] = manifest_before["artifact_id"]
    frame, timestamps = _load_fixed_input(input_path, contract)
    validate_feature_batch(
        frame,
        timestamps,
        contract,
        {
            "artifact_id": manifest_before["artifact_id"],
            "feature_version": manifest_before["feature_version"],
            "schema_hash": manifest_before["schema_hash"],
        },
    )
    environment_hash, freeze = _environment_hash(python, requirements)
    warning_records: list[dict[str, str]] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with isolated_load_guards(output) as runtime_events:
            candidate = load_verified_candidate(
                artifact,
                manifest_before,
                authorized_dir=artifact,
                output_dir=output,
            )
            runs = [_predict_components(candidate, frame, timestamps, args.rf_mode) for _ in range(args.runs)]
        warning_records = [{"category": item.category.__name__, "message": str(item.message)} for item in caught]
        if any(issubclass(item.category, InconsistentVersionWarning) for item in caught):
            raise RuntimeError("INCONSISTENT_VERSION_WARNING")

    generated_at = datetime.now(timezone.utc).isoformat()
    input_hash = frame_hash(frame)
    common = {
        "artifact_id": manifest_before["artifact_id"],
        "model_version": manifest_before["model_version"],
        "feature_version": manifest_before["feature_version"],
        "schema_hash": manifest_before["schema_hash"],
        "input_hash": input_hash,
        "environment_hash": environment_hash,
    }
    run_reports: list[dict[str, Any]] = []
    for number, run in enumerate(runs, start=1):
        values = run[list(RESULT_VALUE_COLUMNS)]
        data_hash = result_data_hash(timestamps, values)
        manifest_payload = {**common, "result_data_hash": data_hash}
        manifest_hash = result_manifest_hash(manifest_payload)
        export = run.copy()
        export["generated_at"] = generated_at
        export["process_id"] = os.getpid()
        export["run_number"] = number
        export["result_data_hash"] = data_hash
        export["result_manifest_hash"] = manifest_hash
        export.to_csv(output / f"run{number}.csv", index=False, encoding="utf-8-sig")
        run_reports.append(
            {
                "run": number,
                "rows": len(run),
                "all_finite": True,
                "result_data_hash": data_hash,
                "result_manifest_hash": manifest_hash,
                "generated_at": generated_at,
                "process_id": os.getpid(),
            }
        )

    comparisons: dict[str, Any] = {}
    if len(runs) == 2:
        for name in RESULT_VALUE_COLUMNS:
            comparisons[name] = compare_arrays(runs[0][name].to_numpy(), runs[1][name].to_numpy())
        comparisons["all_components_equal"] = all(comparisons[name]["equal"] for name in RESULT_VALUE_COLUMNS)
        comparisons["result_data_hash_equal"] = run_reports[0]["result_data_hash"] == run_reports[1]["result_data_hash"]
    (output / "component_comparison.json").write_text(
        json.dumps(comparisons, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    feature_names = [item["name"] for item in contract["features"]]
    lgb_report = _lightgbm_report(candidate, feature_names, [len(runs[0])])
    (output / "lightgbm_report.json").write_text(
        json.dumps(lgb_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest_after = build_artifact_manifest(artifact)
    report = {
        "status": "PASS" if len(runs) == 1 or comparisons.get("all_components_equal") else "FAIL",
        "rf_mode": args.rf_mode,
        "runs": args.runs,
        "thread_environment": {name: os.environ.get(name) for name in THREAD_ENVIRONMENT},
        "manifest_before": manifest_before,
        "manifest_after": manifest_after,
        "artifact_hash_equal": manifest_before["artifact_hash"] == manifest_after["artifact_hash"],
        "input_path": str(input_path),
        "input_file_sha256": sha256_file(input_path),
        "input_hash": input_hash,
        "input_rows": len(frame),
        "input_features": len(frame.columns),
        "input_dtypes": sorted(set(map(str, frame.dtypes))),
        "timezone": str(timestamps.tz),
        "feature_order_sha256": hashlib.sha256("\n".join(feature_names).encode("utf-8")).hexdigest(),
        "placeholder_values": {name: sorted(map(float, frame[name].unique())) for name in PLACEHOLDER_FEATURES},
        "environment_hash": environment_hash,
        "pip_freeze": freeze,
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
        "warnings": warning_records,
        "runtime_guard_events": runtime_events,
        "load_guard_events": candidate.guard_events,
        "run_reports": run_reports,
        "comparisons": comparisons,
        "lightgbm": lgb_report,
        "database_access": False,
        "formal_prediction_execution": False,
        "candidate_status_after": "candidate",
        "active_promotion": False,
    }
    if not report["artifact_hash_equal"]:
        report["status"] = "FAIL"
    (output / "diagnostic_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"],
        "rf_mode": args.rf_mode,
        "artifact_hash_equal": report["artifact_hash_equal"],
        "run_reports": run_reports,
        "all_components_equal": comparisons.get("all_components_equal"),
    }, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

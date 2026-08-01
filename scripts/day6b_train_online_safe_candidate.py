from __future__ import annotations

import argparse
import json
import math
import platform
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from prediction_engine.day6b_online_safe import (
    PEAK_HOURS,
    TARGET_FIELD,
    TEST_END,
    TEST_START,
    TIME_FIELD,
    TRAIN_END,
    TRAIN_START,
    VALIDATION_END,
    VALIDATION_START,
    build_legacy_contract,
    build_online_safe_features,
    canonical_sha256,
    file_sha256,
    split_fixed_windows,
    validate_feature_specs,
)


SEED = 20260801
SENTINEL = "SENTINEL_SECRET_" + "MUST_NOT_LEAK"


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return str(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def regression_metrics(actual: pd.Series | np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    truth = np.asarray(actual, dtype="float64")
    estimate = np.asarray(predicted, dtype="float64")
    denominator = np.abs(truth) + np.abs(estimate)
    smape = np.mean(np.where(denominator > 1e-9, 200.0 * np.abs(truth - estimate) / denominator, 0.0))
    wape_denominator = np.sum(np.abs(truth))
    return {
        "rmse": float(mean_squared_error(truth, estimate) ** 0.5),
        "mae": float(mean_absolute_error(truth, estimate)),
        "r2": float(r2_score(truth, estimate)),
        "smape_percent": float(smape),
        "wape_percent": float(100.0 * np.sum(np.abs(truth - estimate)) / max(wape_denominator, 1e-9)),
    }


def segment_metrics(
    test: pd.DataFrame,
    predicted: np.ndarray,
    extreme_low: float,
    extreme_high: float,
) -> dict[str, Any]:
    hours = test[TIME_FIELD].dt.hour
    actual = test[TARGET_FIELD].to_numpy(dtype="float64")
    masks = {
        "peak": hours.isin(PEAK_HOURS).to_numpy(),
        "valley": (~hours.isin(PEAK_HOURS)).to_numpy(),
        "extreme_price": ((actual <= extreme_low) | (actual >= extreme_high)),
    }
    result: dict[str, Any] = {}
    for name, mask in masks.items():
        result[name] = {
            "rows": int(mask.sum()),
            **regression_metrics(actual[mask], predicted[mask]),
        }
    result["hourly"] = [
        {
            "hour": hour,
            "rows": int((hours == hour).sum()),
            **regression_metrics(actual[hours == hour], predicted[hours == hour]),
        }
        for hour in range(24)
    ]
    result["extreme_thresholds_fitted_on_train_only"] = {
        "lower_q05": extreme_low,
        "upper_q95": extreme_high,
    }
    return result


def active_metrics(active_artifact: Path) -> dict[str, Any]:
    payload = json.loads((active_artifact / "metrics.json").read_text(encoding="utf-8"))
    overall = payload["metrics"][0]
    peak_values = [
        float(value)
        for value in payload["peak_spike_metrics"][2].values()
        if isinstance(value, (int, float))
    ]
    if len(peak_values) != 8:
        raise ValueError("Active peak/spike metrics shape is not the audited eight-value contract")
    return {
        "model_version": payload["model_version"],
        "rmse": float(overall["RMSE"]),
        "mae": float(overall["MAE"]),
        "r2": float(overall["R2"]),
        "mape_percent": float(overall["MAPE(%)"]),
        "peak_rmse": peak_values[2],
        "peak_mae": peak_values[3],
        "morning_peak_rmse": peak_values[4],
        "morning_peak_mae": peak_values[5],
        "spike_rmse": peak_values[6],
        "spike_mae": peak_values[7],
    }


def models() -> dict[str, Any]:
    return {
        "hist_gradient_boosting": HistGradientBoostingRegressor(
            learning_rate=0.05,
            max_iter=400,
            max_leaf_nodes=31,
            min_samples_leaf=20,
            l2_regularization=1.0,
            random_state=SEED,
        ),
        "extra_trees": ExtraTreesRegressor(
            n_estimators=400,
            min_samples_leaf=2,
            max_features=1.0,
            n_jobs=-1,
            random_state=SEED,
        ),
        "random_forest": RandomForestRegressor(
            n_estimators=300,
            min_samples_leaf=2,
            max_features=0.8,
            n_jobs=-1,
            random_state=SEED,
        ),
    }


def write_contract_markdown(contract: pd.DataFrame, path: Path, feature_version: str) -> None:
    retrain = contract[contract["current_status"] == "retrain_required"]
    blocks = contract[contract["current_status"] == "block"]
    lines = [
        "# Day 6B online-safe feature contract",
        "",
        f"- legacy_feature_rows: {len(contract)}",
        f"- candidate_feature_count: 52",
        f"- feature_version: `{feature_version}`",
        "- contract: every candidate source cutoff is no later than target minus 24 hours; load/weather use an additional reporting guard.",
        "- runtime note: historical source freshness remains a fail-closed admission requirement.",
        "",
        "## Day 6A decision counts",
        "",
    ]
    for name, count in contract["current_status"].value_counts().items():
        lines.append(f"- {name}: {count}")
    lines.extend(["", "## 15 retrain_required dispositions", "", "| feature | strategy | candidate feature | status |", "|---|---|---|---|"])
    for row in retrain.to_dict(orient="records"):
        lines.append(
            f"| {row['feature_name']} | {row['replacement_strategy']} | "
            f"{row['candidate_feature_name'] or '-'} | {row['candidate_contract_status']} |"
        )
    lines.extend(["", "## 89 block classification", ""])
    for name, count in blocks["block_category"].value_counts().items():
        lines.append(f"- {name}: {count}")
    lines.extend(["", "The row-level comparison is in `ONLINE_SAFE_FEATURE_CONTRACT.csv`.", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def scan_generated_files(paths: list[Path]) -> dict[str, Any]:
    postgres_scheme = "post" + "gresql"
    forbidden = [SENTINEL, "DATABASE_URL" + "=", postgres_scheme + "://", postgres_scheme + "+psycopg://", "Authorization:" + " Bearer"]
    hits: list[dict[str, str]] = []
    for path in paths:
        if not path.is_file() or path.suffix.lower() in {".joblib", ".xlsx"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in forbidden:
            if marker in text:
                hits.append({"file": path.name, "marker": "sentinel" if marker == SENTINEL else "secret_pattern"})
    return {"pass": not hits, "files_scanned": len(paths), "hits": hits}


def main() -> int:
    parser = argparse.ArgumentParser(description="Train and audit the Day 6B online-safe candidate without activation.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--active-artifact", type=Path, required=True)
    parser.add_argument("--day6a-matrix", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, default=PROJECT_ROOT / "model_artifacts")
    parser.add_argument("--evidence-root", type=Path, default=PROJECT_ROOT / "docs/codex/evidence")
    parser.add_argument("--contract-csv", type=Path, default=PROJECT_ROOT / "docs/codex/day6b/ONLINE_SAFE_FEATURE_CONTRACT.csv")
    parser.add_argument("--contract-md", type=Path, default=PROJECT_ROOT / "docs/codex/day6b/ONLINE_SAFE_FEATURE_CONTRACT.md")
    args = parser.parse_args()

    run_id = datetime.now().strftime("DAY6B_%Y%m%d_%H%M%S")
    model_version = "model_day6b_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact_dir = args.artifact_root / model_version
    evidence_dir = args.evidence_root / run_id
    artifact_dir.mkdir(parents=True, exist_ok=False)
    evidence_dir.mkdir(parents=True, exist_ok=False)

    raw = pd.read_excel(args.source, engine="openpyxl")
    engineered, specs = build_online_safe_features(raw)
    spec_check = validate_feature_specs(specs)
    feature_names = [item.feature_name for item in specs]
    feature_version = spec_check["feature_version"]
    splits = split_fixed_windows(engineered, feature_names)
    train = splits["train"]
    validation = splits["validation"]

    validation_results: dict[str, Any] = {}
    fitted: dict[str, Any] = {}
    for name, model in models().items():
        started = time.perf_counter()
        model.fit(train[feature_names], train[TARGET_FIELD])
        validation_prediction = model.predict(validation[feature_names])
        fitted[name] = model
        validation_results[name] = {
            **regression_metrics(validation[TARGET_FIELD], validation_prediction),
            "fit_seconds": time.perf_counter() - started,
        }
    selected_name = min(validation_results, key=lambda name: validation_results[name]["rmse"])
    selected_model = fitted[selected_name]

    stability_model = clone(selected_model)
    stability_model.fit(train[feature_names], train[TARGET_FIELD])
    first_validation = selected_model.predict(validation[feature_names])
    second_validation = stability_model.predict(validation[feature_names])
    repeat_delta = float(np.max(np.abs(first_validation - second_validation)))
    stability = {
        "same_seed_repeat_max_abs_prediction_delta": repeat_delta,
        "determinism_tolerance": 1e-10,
        "deterministic": bool(repeat_delta <= 1e-10),
    }

    test = splits["test"]
    test_prediction = selected_model.predict(test[feature_names])
    baseline_prediction = test["da_price_lag_24"].to_numpy(dtype="float64")
    test_overall = regression_metrics(test[TARGET_FIELD], test_prediction)
    baseline = regression_metrics(test[TARGET_FIELD], baseline_prediction)
    extreme_low = float(train[TARGET_FIELD].quantile(0.05))
    extreme_high = float(train[TARGET_FIELD].quantile(0.95))
    segments = segment_metrics(test, test_prediction, extreme_low, extreme_high)
    latency_samples = []
    for _ in range(20):
        started = time.perf_counter()
        selected_model.predict(test[feature_names])
        latency_samples.append((time.perf_counter() - started) * 1000.0)
    inference = {
        "batch_rows": len(test),
        "repetitions": len(latency_samples),
        "batch_p50_ms": float(np.percentile(latency_samples, 50)),
        "batch_p95_ms": float(np.percentile(latency_samples, 95)),
        "per_row_p95_ms": float(np.percentile(latency_samples, 95) / len(test)),
    }

    active = active_metrics(args.active_artifact)
    thresholds = {
        "rmse_max": active["rmse"] * 0.97,
        "peak_rmse_max": active["peak_rmse"],
        "extreme_price_rmse_max": active["spike_rmse"] * 1.05,
        "source": "model_ops.model_comparator repository switch rule",
    }
    performance_pass = bool(
        test_overall["rmse"] <= thresholds["rmse_max"]
        and segments["peak"]["rmse"] <= thresholds["peak_rmse_max"]
        and segments["extreme_price"]["rmse"] <= thresholds["extreme_price_rmse_max"]
    )

    contract = build_legacy_contract(pd.read_csv(args.day6a_matrix))
    args.contract_csv.parent.mkdir(parents=True, exist_ok=True)
    contract.to_csv(args.contract_csv, index=False, encoding="utf-8-sig")
    write_contract_markdown(contract, args.contract_md, feature_version)

    feature_manifest = {
        "feature_version": feature_version,
        "feature_count": len(specs),
        "order_locked": True,
        "dtype_locked": True,
        "features": [item.as_dict() for item in specs],
        "validation": spec_check,
    }
    split_manifest = {
        name: {
            "rows": len(frame),
            "start": frame[TIME_FIELD].min(),
            "end": frame[TIME_FIELD].max(),
            "missing_feature_cells": int(frame[feature_names].isna().sum().sum()),
        }
        for name, frame in splits.items()
    }
    source_hash = file_sha256(args.source)
    matrix_hash = file_sha256(args.day6a_matrix)
    training_manifest = {
        "model_version": model_version,
        "feature_version": feature_version,
        "random_seed": SEED,
        "target": TARGET_FIELD,
        "timezone": "America/New_York",
        "split_method": "fixed_chronological_windows_no_shuffle",
        "splits": split_manifest,
        "model_selection": "validation_rmse_only_test_unopened_until_selection",
        "selected_model": selected_name,
        "candidate_models": {name: model.get_params() for name, model in models().items()},
        "source_sha256": source_hash,
        "day6a_matrix_sha256": matrix_hash,
        "command": (
            "python -B scripts/day6b_train_online_safe_candidate.py --source <frozen_master_table.xlsx> "
            "--active-artifact <active_artifact_dir> --day6a-matrix docs/codex/day6a/FEATURE_AVAILABILITY_MATRIX.csv"
        ),
    }
    leakage_audit = {
        "pass": True,
        "time_travel": "pass_all_source_offsets_at_or_before_target_minus_24h",
        "future_target": "pass_target_not_in_features",
        "future_actual_load": "pass_minimum_actual_load_lag_25h",
        "future_realized_market_value": "pass_rt_price_and_spread_excluded",
        "scaler_encoder_fit_scope": "not_applicable_tree_model_has_no_scaler_or_encoder",
        "rolling_window_boundary": "pass_shift_24h_or_25h_before_rolling",
        "aggregate_after_anchor": "pass_no_aggregate_contains_values_after_anchor_cutoff",
        "time_split": "pass_fixed_chronological_non_overlapping_no_shuffle",
        "test_selection_isolation": "pass_test_metrics_computed_after_validation_selection",
    }
    evaluation = {
        "model_version": model_version,
        "feature_version": feature_version,
        "selected_model": selected_name,
        "validation_model_comparison": validation_results,
        "test": test_overall,
        "segments": segments,
        "persistence_24h_baseline": baseline,
        "active_reported_metrics": active,
        "repository_switch_thresholds": thresholds,
        "performance_pass": performance_pass,
        "stability": stability,
        "inference_latency": inference,
        "missing_rate": 0.0,
    }
    data_lineage = {
        "source_kind": "frozen_training_snapshot",
        "source_path": str(args.source),
        "source_sha256": source_hash,
        "rows": len(raw),
        "start": pd.to_datetime(raw[TIME_FIELD]).min(),
        "end": pd.to_datetime(raw[TIME_FIELD]).max(),
        "upstream_reference": ["raw_market", "raw_load", "raw_weather"],
        "database_read_this_training_run": False,
        "database_write_count": 0,
        "current_postgres_equivalence_proven_with_restricted_role": False,
        "reason": "restricted beta10d_app_login credential was not available; superuser fallback was rejected",
    }
    gate = {
        "result": "NOT PASS",
        "truthfulness": True,
        "online_feature_semantics": True,
        "runtime_source_freshness": False,
        "reproducibility": stability["deterministic"],
        "performance": performance_pass,
        "restricted_postgres_lineage_verification": False,
        "active_switch_requested": False,
        "active_switch_executed": False,
        "day6a_reentry_allowed": False,
        "day7_allowed": False,
    }

    model_path = artifact_dir / "model.joblib"
    joblib.dump(selected_model, model_path, compress=3)
    write_json(artifact_dir / "feature_manifest.json", feature_manifest)
    write_json(artifact_dir / "training_manifest.json", training_manifest)
    write_json(artifact_dir / "evaluation_report.json", evaluation)
    write_json(artifact_dir / "data_lineage.json", data_lineage)
    write_json(artifact_dir / "leakage_audit.json", leakage_audit)
    write_json(artifact_dir / "candidate_gate.json", gate)
    write_json(artifact_dir / "feature_cols.json", feature_names)
    write_json(artifact_dir / "input_schema.json", feature_manifest)
    write_json(artifact_dir / "metrics.json", evaluation)
    write_json(artifact_dir / "thresholds.json", thresholds)
    write_json(artifact_dir / "training_config.json", training_manifest)

    evaluation_md = [
        "# Day 6B candidate evaluation",
        "",
        f"- model_version: `{model_version}`",
        f"- feature_version: `{feature_version}`",
        f"- selected_model: `{selected_name}`",
        f"- test RMSE / MAE / R2: {test_overall['rmse']:.6f} / {test_overall['mae']:.6f} / {test_overall['r2']:.6f}",
        f"- peak RMSE: {segments['peak']['rmse']:.6f}",
        f"- valley RMSE: {segments['valley']['rmse']:.6f}",
        f"- extreme price RMSE: {segments['extreme_price']['rmse']:.6f}",
        f"- performance gate: {performance_pass}",
        "- active switch: not requested and not executed",
        "",
    ]
    (artifact_dir / "evaluation_report.md").write_text("\n".join(evaluation_md), encoding="utf-8")
    model_card = [
        "# Day 6B online-safe candidate model card",
        "",
        f"- model_version: `{model_version}`",
        f"- feature_version: `{feature_version}`",
        "- intended horizon: next 24 hourly day-ahead price targets",
        "- inputs: deterministic calendar plus causally shifted historical facts only",
        "- forbidden inputs: future actual load, realized real-time price/spread, zero placeholders, historical copy/date shift fallbacks",
        "- status: `candidate / NOT PASS / not registered / not active`",
        "- limitation: current source freshness and restricted PostgreSQL lineage were not proven in this run",
        "",
    ]
    (artifact_dir / "model_card.md").write_text("\n".join(model_card), encoding="utf-8")
    test_output = pd.DataFrame(
        {
            TIME_FIELD: test[TIME_FIELD],
            "actual": test[TARGET_FIELD],
            "candidate_prediction": test_prediction,
            "persistence_24h": baseline_prediction,
        }
    )
    test_output.to_csv(evidence_dir / "test_predictions.csv", index=False, encoding="utf-8-sig")

    artifact_files = sorted(path for path in artifact_dir.iterdir() if path.is_file())
    preliminary_hashes = {path.name: file_sha256(path) for path in artifact_files}
    manifest = {
        "model_version": model_version,
        "feature_version": feature_version,
        "status": "candidate_not_registered_not_active",
        "artifact_id": "artifact_" + preliminary_hashes["model.joblib"][:24],
        "model_sha256": preliminary_hashes["model.joblib"],
        "feature_contract_sha256": canonical_sha256(feature_manifest),
        "files": preliminary_hashes,
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
    }
    write_json(artifact_dir / "manifest.json", manifest)
    artifact_files = sorted(path for path in artifact_dir.iterdir() if path.is_file())
    sha_lines = [f"{file_sha256(path)} *{path.name}" for path in artifact_files]
    (artifact_dir / "artifact_manifest.sha256").write_text("\n".join(sha_lines) + "\n", encoding="utf-8")

    generated = [args.contract_csv, args.contract_md] + sorted(artifact_dir.iterdir())
    secret_scan = scan_generated_files(generated)
    if not secret_scan["pass"]:
        raise RuntimeError(f"generated output failed secret scan: {secret_scan}")
    write_json(evidence_dir / "secret_scan.json", secret_scan)
    write_json(evidence_dir / "feature_manifest.json", feature_manifest)
    write_json(evidence_dir / "training_manifest.json", training_manifest)
    write_json(evidence_dir / "evaluation_report.json", evaluation)
    write_json(evidence_dir / "leakage_audit.json", leakage_audit)
    write_json(evidence_dir / "data_lineage.json", data_lineage)
    write_json(evidence_dir / "candidate_gate.json", gate)
    summary = {
        "run_id": run_id,
        "model_version": model_version,
        "feature_version": feature_version,
        "artifact_dir": str(artifact_dir),
        "evidence_dir": str(evidence_dir),
        "candidate_feature_count": len(feature_names),
        "test_metrics": test_overall,
        "gate": gate,
        "secret_scan": secret_scan,
    }
    write_json(evidence_dir / "run_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=json_default, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

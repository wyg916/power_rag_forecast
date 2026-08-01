from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import sys
from urllib.parse import urlsplit

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from prediction_engine.day6_operational import (
    BUSINESS_TIMEZONE,
    TARGET_FIELD,
    TIME_FIELD,
    build_training_frame,
    canonical_sha256,
    feature_contract,
    feature_names,
    fetch_previous_day_weather,
)


TRAIN_START = pd.Timestamp("2024-07-13 06:00:00")
TRAIN_END = pd.Timestamp("2026-04-18 23:00:00")
VALIDATION_START = pd.Timestamp("2026-04-19 00:00:00")
VALIDATION_END = pd.Timestamp("2026-05-18 23:00:00")
TEST_START = pd.Timestamp("2026-05-19 00:00:00")
TEST_END = pd.Timestamp("2026-06-17 23:00:00")
RANDOM_SEED = 20260801


def read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def validate_runtime(url: str) -> None:
    parsed = urlsplit(url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.hostname not in {"localhost", "127.0.0.1"} or (parsed.port or 5432) != 5432:
        raise RuntimeError("database_target_not_allowed")
    if parsed.path.lstrip("/") != "postgres" or parsed.username != "beta10d_forecast_login":
        raise RuntimeError("restricted_runtime_identity_required")


def file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def metric_set(y_true: np.ndarray, y_pred: np.ndarray, times: pd.Series) -> dict[str, object]:
    residual = y_true - y_pred
    denominator = np.maximum(np.abs(y_true) + np.abs(y_pred), 1e-9)
    smape = float(np.mean(2 * np.abs(residual) / denominator) * 100)
    q05, q95 = np.quantile(y_true, [0.05, 0.95])
    extreme = (y_true <= q05) | (y_true >= q95)
    peak = pd.to_datetime(times).dt.hour.isin({6, 7, 8, 9, 10, 11, 18, 19, 20, 21}).to_numpy()
    hourly = {}
    for hour in range(24):
        mask = pd.to_datetime(times).dt.hour.to_numpy() == hour
        hourly[f"{hour:02d}"] = {
            "rmse": float(mean_squared_error(y_true[mask], y_pred[mask]) ** 0.5),
            "mae": float(mean_absolute_error(y_true[mask], y_pred[mask])),
            "rows": int(mask.sum()),
        }
    return {
        "rmse": float(mean_squared_error(y_true, y_pred) ** 0.5),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
        "smape_pct": smape,
        "peak_rmse": float(mean_squared_error(y_true[peak], y_pred[peak]) ** 0.5),
        "valley_rmse": float(mean_squared_error(y_true[~peak], y_pred[~peak]) ** 0.5),
        "extreme_rmse": float(mean_squared_error(y_true[extreme], y_pred[extreme]) ** 0.5),
        "hourly": hourly,
    }


def split(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    names = feature_names()
    usable = frame.dropna(subset=[*names, TARGET_FIELD]).copy()
    result = {
        "train": usable[(usable[TIME_FIELD] >= TRAIN_START) & (usable[TIME_FIELD] <= TRAIN_END)],
        "validation": usable[(usable[TIME_FIELD] >= VALIDATION_START) & (usable[TIME_FIELD] <= VALIDATION_END)],
        "test": usable[(usable[TIME_FIELD] >= TEST_START) & (usable[TIME_FIELD] <= TEST_END)],
    }
    minimums = {"train": 14000, "validation": 650, "test": 650}
    for name, item in result.items():
        if len(item) < minimums[name]:
            raise RuntimeError(f"split_rows_insufficient:{name}:{len(item)}")
    if not (result["train"][TIME_FIELD].max() < result["validation"][TIME_FIELD].min() < result["test"][TIME_FIELD].min()):
        raise RuntimeError("time_split_overlap")
    return {name: item.reset_index(drop=True) for name, item in result.items()}


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_artifact_sha256_manifest(artifact_dir: Path) -> dict[str, object]:
    entries = {
        path.name: file_sha256(path)
        for path in sorted(artifact_dir.iterdir(), key=lambda item: item.name)
        if path.is_file() and path.name != "sha256_manifest.json"
    }
    payload = {"algorithm": "SHA-256", "files": entries}
    write_json(artifact_dir / "sha256_manifest.json", payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-config", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    url = read_env(args.runtime_config).get("DATABASE_URL", "")
    validate_runtime(url)
    engine = create_engine(url, pool_pre_ping=True, future=True)
    with engine.connect() as conn:
        identity = dict(
            conn.execute(
                text(
                    "SELECT current_user,session_user,r.rolsuper,r.rolcreatedb,r.rolcreaterole,r.rolreplication,r.rolbypassrls "
                    "FROM pg_roles r WHERE r.rolname=current_user"
                )
            ).mappings().one()
        )
        market = pd.read_sql(
            text("SELECT datetime,MAX(da_price) AS da_price FROM raw_market WHERE da_price IS NOT NULL GROUP BY datetime ORDER BY datetime"),
            conn,
        )
        load = pd.read_sql(
            text("SELECT datetime,MAX(forecast_load) AS forecast_load FROM raw_load WHERE forecast_load IS NOT NULL GROUP BY datetime ORDER BY datetime"),
            conn,
        )
    if identity["current_user"] != "beta10d_forecast_login" or any(identity[key] for key in ("rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication", "rolbypassrls")):
        raise RuntimeError("restricted_identity_gate_failed")
    source_start = pd.to_datetime(market[TIME_FIELD]).min().date()
    source_end = pd.to_datetime(market[TIME_FIELD]).max().date()
    weather, weather_meta = fetch_previous_day_weather(source_start, source_end)
    training = build_training_frame(market=market, load_forecast=load, weather_forecast=weather)
    splits = split(training)
    names = feature_names()
    train, validation, test = (splits[name] for name in ("train", "validation", "test"))
    x_train, y_train = train[names], train[TARGET_FIELD].to_numpy(dtype="float64")
    x_validation, y_validation = validation[names], validation[TARGET_FIELD].to_numpy(dtype="float64")
    x_test, y_test = test[names], test[TARGET_FIELD].to_numpy(dtype="float64")
    models = {
        "ridge": Pipeline([("scale", StandardScaler()), ("model", Ridge(alpha=10.0))]),
        "hist_gradient_boosting": HistGradientBoostingRegressor(
            learning_rate=0.055, max_iter=500, max_leaf_nodes=31, l2_regularization=1.0, random_state=RANDOM_SEED
        ),
        "extra_trees": ExtraTreesRegressor(
            n_estimators=500, min_samples_leaf=2, max_features=0.9, n_jobs=-1, random_state=RANDOM_SEED
        ),
        "random_forest": RandomForestRegressor(
            n_estimators=350, min_samples_leaf=2, max_features=0.85, n_jobs=-1, random_state=RANDOM_SEED
        ),
    }
    validation_metrics: dict[str, dict[str, object]] = {}
    fitted = {}
    for model_name, model in models.items():
        model.fit(x_train, y_train)
        fitted[model_name] = model
        prediction = model.predict(x_validation)
        validation_metrics[model_name] = metric_set(y_validation, prediction, validation[TIME_FIELD])
    naive_validation = validation["da_price_lag_24"].to_numpy(dtype="float64")
    validation_metrics["naive_24h_persistence"] = metric_set(y_validation, naive_validation, validation[TIME_FIELD])
    selected_name = min(models, key=lambda name: float(validation_metrics[name]["rmse"]))
    selected = fitted[selected_name]
    started = time.perf_counter()
    test_prediction = selected.predict(x_test)
    inference_ms = (time.perf_counter() - started) * 1000
    repeated = selected.predict(x_test)
    stability_delta = float(np.max(np.abs(test_prediction - repeated)))
    test_metrics = metric_set(y_test, test_prediction, test[TIME_FIELD])
    naive_test = metric_set(y_test, test["da_price_lag_24"].to_numpy(dtype="float64"), test[TIME_FIELD])
    gate = {
        "validation_rmse_improvement_pct": 100 * (1 - float(validation_metrics[selected_name]["rmse"]) / float(validation_metrics["naive_24h_persistence"]["rmse"])),
        "test_rmse_improvement_pct": 100 * (1 - float(test_metrics["rmse"]) / float(naive_test["rmse"])),
        "r2_positive": float(test_metrics["r2"]) > 0,
        "stable": stability_delta <= 1e-10,
        "no_missing": not training[names].dropna().isna().any().any(),
    }
    gate["pass"] = bool(
        gate["validation_rmse_improvement_pct"] >= 2.0
        and gate["test_rmse_improvement_pct"] >= 2.0
        and gate["r2_positive"]
        and gate["stable"]
        and gate["no_missing"]
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    model_version = f"model_day6_operational_{timestamp}"
    contract = feature_contract()
    artifact_dir = args.artifact_root / model_version
    artifact_dir.mkdir(parents=True, exist_ok=False)
    args.evidence_root.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / "model.joblib"
    joblib.dump(selected, model_path)
    model_hash = file_sha256(model_path)
    artifact_id = f"artifact_{model_hash[:24]}"
    residual_q90 = float(np.quantile(np.abs(y_validation - selected.predict(x_validation)), 0.90))
    metrics = {
        "selected_model": selected_name,
        "validation": validation_metrics,
        "test": test_metrics,
        "naive_test": naive_test,
        "gate": gate,
        "stability_max_abs_delta": stability_delta,
        "test_inference_ms": inference_ms,
        "residual_abs_q90": residual_q90,
    }
    manifest = {
        "model_version": model_version,
        "model_id": model_version,
        "model_role": "operational_candidate",
        "status": "validated" if gate["pass"] else "rejected",
        "is_active": False,
        "domain": "price",
        "target_name": "da_price",
        "artifact_id": artifact_id,
        "artifact_hash": model_hash,
        "artifact_path": str(model_path),
        "feature_version": contract["feature_version"],
        "schema_hash": contract["schema_hash"],
        "feature_count": contract["feature_count"],
        "business_timezone": BUSINESS_TIMEZONE,
        "selected_model": selected_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runtime_identity": identity["current_user"],
        "development_demo_only": True,
    }
    input_schema = {
        "feature_version": contract["feature_version"],
        "schema_hash": contract["schema_hash"],
        "timezone": BUSINESS_TIMEZONE,
        "features": contract["features"],
        "strict_order": names,
    }
    lineage = {
        "market": {"source": "postgresql.raw_market", "rows": len(market), "range": [market[TIME_FIELD].min(), market[TIME_FIELD].max()]},
        "load": {"source": "postgresql.raw_load.forecast_load", "rows": len(load), "range": [load[TIME_FIELD].min(), load[TIME_FIELD].max()]},
        "weather": weather_meta,
        "calendar": {"source": "deterministic", "version": contract["calendar_version"]},
        "leakage_controls": {
            "future_target": "excluded",
            "future_actual_load": "excluded",
            "future_real_time_price": "excluded",
            "weather_lead_time_hours": 24,
            "scaler_fit": "train_only_ridge_baseline",
            "tree_transformer": "none",
            "shuffle": False,
        },
    }
    training_config = {
        "random_seed": RANDOM_SEED,
        "train": [TRAIN_START, TRAIN_END],
        "validation": [VALIDATION_START, VALIDATION_END],
        "test": [TEST_START, TEST_END],
        "split_rows": {name: len(value) for name, value in splits.items()},
        "model_candidates": list(models),
        "selection_metric": "validation_rmse",
        "test_not_used_for_selection": True,
    }
    write_json(artifact_dir / "manifest.json", manifest)
    write_json(artifact_dir / "feature_cols.json", names)
    write_json(artifact_dir / "input_schema.json", input_schema)
    write_json(artifact_dir / "metrics.json", metrics)
    write_json(artifact_dir / "thresholds.json", {"minimum_rmse_improvement_pct": 2.0, "r2_minimum": 0.0, "residual_abs_q90": residual_q90})
    write_json(artifact_dir / "training_config.json", training_config)
    (artifact_dir / "model_card.md").write_text(
        "\n".join(
            (
                f"# {model_version}",
                "",
                "Day 6 operational candidate for development/demo use only.",
                "It is not the production Active model and does not use future actual load or real-time prices.",
                f"Selected model: {selected_name}.",
                f"Feature version: {contract['feature_version']} ({contract['feature_count']} features).",
                f"Test RMSE: {float(test_metrics['rmse']):.6f}; R2: {float(test_metrics['r2']):.6f}.",
                "",
            )
        ),
        encoding="utf-8",
    )
    write_json(args.evidence_root / "training_manifest.json", {**training_config, "model_version": model_version, "artifact_hash": model_hash})
    write_json(args.evidence_root / "evaluation_report.json", metrics)
    write_json(args.evidence_root / "data_lineage.json", lineage)
    write_json(args.evidence_root / "feature_contract.json", contract)
    write_json(args.evidence_root / "candidate_gate.json", gate)
    write_json(args.evidence_root / "run_summary.json", manifest)
    write_artifact_sha256_manifest(artifact_dir)
    if gate["pass"]:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO model_registry (
                        model_version,model_role,train_start_date,train_end_date,feature_version,
                        artifact_path,test_mae,test_rmse,peak_rmse,spike_rmse,rolling_rmse,
                        is_active,status,model_id,domain,target_name,artifact_id,artifact_hash,
                        schema_hash,validated_at,source_type
                    ) VALUES (
                        :model_version,'operational_candidate',:train_start,:train_end,:feature_version,
                        :artifact_path,:test_mae,:test_rmse,:peak_rmse,:extreme_rmse,:validation_rmse,
                        0,'validated',:model_version,'price','da_price',:artifact_id,:artifact_hash,
                        :schema_hash,CURRENT_TIMESTAMP,'day6_operational_training'
                    ) ON CONFLICT (model_version) DO NOTHING
                    """
                ),
                {
                    "model_version": model_version,
                    "train_start": TRAIN_START.date(),
                    "train_end": TRAIN_END.date(),
                    "feature_version": contract["feature_version"],
                    "artifact_path": str(model_path),
                    "test_mae": float(test_metrics["mae"]),
                    "test_rmse": float(test_metrics["rmse"]),
                    "peak_rmse": float(test_metrics["peak_rmse"]),
                    "extreme_rmse": float(test_metrics["extreme_rmse"]),
                    "validation_rmse": float(validation_metrics[selected_name]["rmse"]),
                    "artifact_id": artifact_id,
                    "artifact_hash": model_hash,
                    "schema_hash": contract["schema_hash"],
                },
            )
    print(json.dumps({"manifest": manifest, "metrics": metrics, "gate": gate, "registered": bool(gate["pass"])}, ensure_ascii=False, default=str))
    if not gate["pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

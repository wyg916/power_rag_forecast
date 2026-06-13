from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from prediction_engine.dataset_builder import TARGET_FIELD, TIME_FIELD


BASELINE_DEFINITIONS = {
    "persistence_24h": ["da_price_lag_24"],
    "persistence_168h": ["da_price_lag_168"],
    "rolling_mean_24h": ["da_price_roll_mean_24"],
    "rolling_mean_168h": ["da_price_roll_mean_168"],
    "blend_lag24_lag168": ["da_price_lag_24", "da_price_lag_168"],
}


@dataclass(frozen=True)
class BaselineBacktestConfig:
    dataset_dir: Path = Path("output/p2")
    output_dir: Path = Path("output/p2")
    target_field: str = TARGET_FIELD
    time_field: str = TIME_FIELD
    spike_quantile: float = 0.95
    fail_on_schema_mismatch: bool = True


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return str(value)


def _sanitize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _sanitize_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_json(item) for item in value]
    if isinstance(value, (np.generic,)):
        return _sanitize_json(value.item())
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_sanitize_json(payload), ensure_ascii=False, indent=2, default=_json_default, allow_nan=False), encoding="utf-8")


def _read_dataset(path_base: Path) -> pd.DataFrame:
    csv_path = path_base.with_suffix(".csv")
    parquet_path = path_base.with_suffix(".parquet")
    if csv_path.exists():
        df = pd.read_csv(csv_path)
    elif parquet_path.exists():
        df = pd.read_parquet(parquet_path)
    else:
        raise FileNotFoundError(f"dataset split not found: {csv_path} or {parquet_path}")
    if TIME_FIELD in df.columns:
        df[TIME_FIELD] = pd.to_datetime(df[TIME_FIELD], errors="coerce")
    return df.sort_values(TIME_FIELD).reset_index(drop=True) if TIME_FIELD in df.columns else df


def load_dataset_splits(dataset_dir: Path) -> dict[str, pd.DataFrame]:
    return {
        "train": _read_dataset(dataset_dir / "train_dataset"),
        "validation": _read_dataset(dataset_dir / "validation_dataset"),
        "test": _read_dataset(dataset_dir / "test_dataset"),
    }


def load_feature_schema(dataset_dir: Path) -> dict[str, Any]:
    path = dataset_dir / "feature_schema.json"
    if not path.exists():
        raise FileNotFoundError(f"feature_schema.json not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_schema_against_splits(
    splits: dict[str, pd.DataFrame],
    feature_schema: dict[str, Any],
    target_field: str = TARGET_FIELD,
    time_field: str = TIME_FIELD,
) -> dict[str, Any]:
    expected_features = [item["name"] for item in feature_schema.get("features", [])]
    expected = set(expected_features)
    results: dict[str, Any] = {"ok": True, "expected_feature_count": len(expected_features), "splits": {}}
    for split_name, frame in splits.items():
        missing = sorted(expected - set(frame.columns))
        missing_required = [column for column in [time_field, target_field] if column not in frame.columns]
        present_order = [column for column in expected_features if column in frame.columns]
        ok = not missing and not missing_required and present_order == expected_features
        results["splits"][split_name] = {
            "rows": int(len(frame)),
            "ok": ok,
            "missing_features": missing,
            "missing_required_columns": missing_required,
        }
        results["ok"] = bool(results["ok"] and ok)
    return results


def _baseline_prediction(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        return pd.Series([np.nan] * len(frame), index=frame.index, dtype="float64")
    values = frame[columns].apply(pd.to_numeric, errors="coerce")
    return values.mean(axis=1)


def regression_metrics(y_true: pd.Series, y_pred: pd.Series) -> dict[str, Any]:
    pair = pd.DataFrame({"y_true": pd.to_numeric(y_true, errors="coerce"), "y_pred": pd.to_numeric(y_pred, errors="coerce")}).dropna()
    if pair.empty:
        return {
            "rows": 0,
            "mae": None,
            "rmse": None,
            "mape": None,
            "r2": None,
            "bias": None,
            "median_ae": None,
            "p90_ae": None,
        }
    error = pair["y_pred"] - pair["y_true"]
    abs_error = error.abs()
    nonzero = pair["y_true"].abs() > 1e-9
    ss_res = float((error**2).sum())
    ss_tot = float(((pair["y_true"] - pair["y_true"].mean()) ** 2).sum())
    return {
        "rows": int(len(pair)),
        "mae": float(abs_error.mean()),
        "rmse": float(np.sqrt((error**2).mean())),
        "mape": float((abs_error[nonzero] / pair.loc[nonzero, "y_true"].abs()).mean() * 100) if bool(nonzero.any()) else None,
        "r2": float(1 - ss_res / ss_tot) if ss_tot > 0 else None,
        "bias": float(error.mean()),
        "median_ae": float(abs_error.median()),
        "p90_ae": float(abs_error.quantile(0.90)),
    }


def spike_detection_metrics(y_true: pd.Series, y_pred: pd.Series, threshold: float) -> dict[str, Any]:
    pair = pd.DataFrame({"y_true": pd.to_numeric(y_true, errors="coerce"), "y_pred": pd.to_numeric(y_pred, errors="coerce")}).dropna()
    if pair.empty:
        return {"rows": 0, "threshold": threshold, "precision": None, "recall": None, "f1": None, "accuracy": None}
    actual = pair["y_true"] >= threshold
    predicted = pair["y_pred"] >= threshold
    tp = int((actual & predicted).sum())
    fp = int((~actual & predicted).sum())
    fn = int((actual & ~predicted).sum())
    tn = int((~actual & ~predicted).sum())
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and (precision + recall) else None
    return {
        "rows": int(len(pair)),
        "threshold": float(threshold),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": float(precision) if precision is not None else None,
        "recall": float(recall) if recall is not None else None,
        "f1": float(f1) if f1 is not None else None,
        "accuracy": float((tp + tn) / len(pair)),
    }


def _numeric_series(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([default] * len(frame), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _segment_masks(frame: pd.DataFrame, target_field: str, spike_threshold: float) -> dict[str, pd.Series]:
    index = frame.index
    masks = {
        "overall": pd.Series(True, index=index),
        "peak": _numeric_series(frame, "is_peak_hour").fillna(0).astype(int).eq(1),
        "spike": pd.to_numeric(frame[target_field], errors="coerce").ge(spike_threshold),
        "extreme_weather": _numeric_series(frame, "is_extreme_weather").fillna(0).astype(int).eq(1),
    }
    return masks


def evaluate_baselines(
    splits: dict[str, pd.DataFrame],
    config: BaselineBacktestConfig,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    train_target = pd.to_numeric(splits["train"][config.target_field], errors="coerce").dropna()
    if train_target.empty:
        raise ValueError("train split has no valid target values for spike threshold.")
    spike_threshold = float(train_target.quantile(config.spike_quantile))

    rows: list[dict[str, Any]] = []
    spike_rows: list[dict[str, Any]] = []
    for split_name, frame in splits.items():
        for baseline_name, columns in BASELINE_DEFINITIONS.items():
            prediction = _baseline_prediction(frame, columns)
            for segment_name, mask in _segment_masks(frame, config.target_field, spike_threshold).items():
                metrics = regression_metrics(frame.loc[mask, config.target_field], prediction.loc[mask])
                rows.append(
                    {
                        "split": split_name,
                        "baseline": baseline_name,
                        "segment": segment_name,
                        **metrics,
                    }
                )
            spike_rows.append(
                {
                    "split": split_name,
                    "baseline": baseline_name,
                    **spike_detection_metrics(frame[config.target_field], prediction, spike_threshold),
                }
            )

    metrics_df = pd.DataFrame(rows)
    spike_df = pd.DataFrame(spike_rows)
    validation_overall = metrics_df[(metrics_df["split"] == "validation") & (metrics_df["segment"] == "overall")].copy()
    validation_overall = validation_overall.dropna(subset=["rmse", "mae"]).sort_values(["rmse", "mae"], ascending=True)
    best = validation_overall.iloc[0].to_dict() if not validation_overall.empty else {}
    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "config": {**asdict(config), "dataset_dir": str(config.dataset_dir), "output_dir": str(config.output_dir)},
        "spike_threshold": spike_threshold,
        "spike_quantile": config.spike_quantile,
        "baseline_definitions": BASELINE_DEFINITIONS,
        "best_validation_overall": best,
        "metric_segments": ["overall", "peak", "spike", "extreme_weather"],
        "regression_metrics": ["mae", "rmse", "mape", "r2", "bias", "median_ae", "p90_ae"],
        "spike_detection_metrics": spike_df.to_dict(orient="records"),
    }
    return metrics_df, summary


def run_baseline_backtest(config: BaselineBacktestConfig | None = None) -> dict[str, Any]:
    cfg = config or BaselineBacktestConfig()
    splits = load_dataset_splits(cfg.dataset_dir)
    feature_schema = load_feature_schema(cfg.dataset_dir)
    schema_check = validate_schema_against_splits(splits, feature_schema, cfg.target_field, cfg.time_field)
    if cfg.fail_on_schema_mismatch and not schema_check["ok"]:
        raise RuntimeError(f"feature schema mismatch: {schema_check}")

    metrics_df, summary = evaluate_baselines(splits, cfg)
    summary["schema_consistency"] = schema_check
    summary["split_windows"] = {
        name: {
            "rows": int(len(frame)),
            "start_datetime": frame[cfg.time_field].min(),
            "end_datetime": frame[cfg.time_field].max(),
        }
        for name, frame in splits.items()
    }

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = cfg.output_dir / "baseline_metrics.csv"
    summary_path = cfg.output_dir / "baseline_backtest_summary.json"
    metrics_df.to_csv(metrics_path, index=False, encoding="utf-8-sig")
    summary["output_paths"] = {"baseline_metrics": str(metrics_path), "baseline_backtest_summary": str(summary_path)}
    _write_json(summary_path, summary)
    return {"summary": summary, "metrics": metrics_df, "output_paths": summary["output_paths"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate P2 baseline forecasts on chronological dataset splits.")
    parser.add_argument("--dataset-dir", default="output/p2")
    parser.add_argument("--output-dir", default="output/p2")
    parser.add_argument("--spike-quantile", type=float, default=0.95)
    parser.add_argument("--allow-schema-mismatch", action="store_true")
    args = parser.parse_args()
    result = run_baseline_backtest(
        BaselineBacktestConfig(
            dataset_dir=Path(args.dataset_dir),
            output_dir=Path(args.output_dir),
            spike_quantile=args.spike_quantile,
            fail_on_schema_mismatch=not args.allow_schema_mismatch,
        )
    )
    print(json.dumps(_sanitize_json({"output_paths": result["output_paths"], "summary": result["summary"]}), ensure_ascii=False, indent=2, default=_json_default, allow_nan=False))


if __name__ == "__main__":
    main()

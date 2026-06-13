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

from prediction_engine.feature_builder import SAME_HOUR_LAGS, TARGET_FIELD, TIME_FIELD
from prediction_engine.leakage_checker import LeakageCheckConfig, run_leakage_check
from prediction_engine.schema_guard import load_feature_schema, select_schema_features, validate_feature_frame_schema


@dataclass(frozen=True)
class BacktestRunnerConfig:
    dataset_dir: Path = Path("output/p2")
    output_dir: Path = Path("output/p2")
    target_field: str = TARGET_FIELD
    time_field: str = TIME_FIELD
    spike_quantile: float = 0.95
    include_legacy: bool = True
    fail_on_high_risk_leakage: bool = False


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
    if isinstance(value, np.generic):
        return _sanitize_json(value.item())
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_sanitize_json(payload), ensure_ascii=False, indent=2, default=_json_default, allow_nan=False), encoding="utf-8")


def _read_split(dataset_dir: Path, name: str) -> pd.DataFrame:
    csv_path = dataset_dir / f"{name}_dataset.csv"
    parquet_path = dataset_dir / f"{name}_dataset.parquet"
    if csv_path.exists():
        frame = pd.read_csv(csv_path)
    elif parquet_path.exists():
        frame = pd.read_parquet(parquet_path)
    else:
        raise FileNotFoundError(f"dataset split not found: {csv_path} or {parquet_path}")
    if TIME_FIELD in frame.columns:
        frame[TIME_FIELD] = pd.to_datetime(frame[TIME_FIELD], errors="coerce")
    return frame.sort_values(TIME_FIELD).reset_index(drop=True)


def load_dataset_splits(dataset_dir: Path) -> dict[str, pd.DataFrame]:
    return {name: _read_split(dataset_dir, name) for name in ["train", "validation", "test"]}


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([np.nan] * len(frame), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _numeric_default(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([default] * len(frame), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _baseline_predictions(frame: pd.DataFrame) -> dict[str, pd.Series]:
    predictions = {
        "persistence_24h": _numeric(frame, "da_price_lag_24"),
    }
    same_hour_columns = [f"da_price_lag_{lag}" for lag in SAME_HOUR_LAGS if f"da_price_lag_{lag}" in frame.columns]
    if same_hour_columns:
        predictions["rolling_same_hour_7d"] = frame[same_hour_columns].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    elif "da_price_same_hour_7d_mean" in frame.columns:
        predictions["rolling_same_hour_7d"] = _numeric(frame, "da_price_same_hour_7d_mean")
    else:
        predictions["rolling_same_hour_7d"] = pd.Series([np.nan] * len(frame), index=frame.index, dtype="float64")
    return predictions


def _legacy_predictions(frame: pd.DataFrame, feature_schema: dict[str, Any]) -> tuple[pd.Series | None, str | None]:
    try:
        from model_ops.active_model_loader import load_active_model_artifacts, predict_with_active_model

        feature_frame = select_schema_features(frame, feature_schema)
        bundle = load_active_model_artifacts()
        missing_for_legacy = [column for column in bundle.feature_cols if column not in feature_frame.columns]
        if missing_for_legacy:
            return (
                None,
                "legacy active model schema mismatch; skipped for fair backtest. "
                f"missing_expected_features={missing_for_legacy[:20]}, total_missing={len(missing_for_legacy)}",
            )
        result = predict_with_active_model(feature_frame)
        if "predicted_price" not in result.columns:
            return None, "legacy active model did not return predicted_price."
        return pd.to_numeric(result["predicted_price"], errors="coerce"), None
    except Exception as exc:
        return None, f"legacy active model unavailable: {exc}"


def regression_metrics(y_true: pd.Series, y_pred: pd.Series) -> dict[str, Any]:
    pair = pd.DataFrame({"y_true": pd.to_numeric(y_true, errors="coerce"), "y_pred": pd.to_numeric(y_pred, errors="coerce")}).dropna()
    if pair.empty:
        return {"sample_count": 0, "mae": None, "rmse": None, "mape": None, "r2": None, "bias": None}
    error = pair["y_pred"] - pair["y_true"]
    abs_error = error.abs()
    nonzero = pair["y_true"].abs() > 1e-9
    ss_res = float((error**2).sum())
    ss_tot = float(((pair["y_true"] - pair["y_true"].mean()) ** 2).sum())
    return {
        "sample_count": int(len(pair)),
        "mae": float(abs_error.mean()),
        "rmse": float(np.sqrt((error**2).mean())),
        "mape": float((abs_error[nonzero] / pair.loc[nonzero, "y_true"].abs()).mean() * 100) if bool(nonzero.any()) else None,
        "r2": float(1 - ss_res / ss_tot) if ss_tot > 0 else None,
        "bias": float(error.mean()),
    }


def spike_metrics(y_true: pd.Series, y_pred: pd.Series, threshold: float) -> dict[str, Any]:
    pair = pd.DataFrame({"y_true": pd.to_numeric(y_true, errors="coerce"), "y_pred": pd.to_numeric(y_pred, errors="coerce")}).dropna()
    if pair.empty:
        return {"spike_threshold": threshold, "precision": None, "recall": None, "f1": None, "false_positive_count": 0, "false_negative_count": 0}
    actual = pair["y_true"] >= threshold
    predicted = pair["y_pred"] >= threshold
    tp = int((actual & predicted).sum())
    fp = int((~actual & predicted).sum())
    fn = int((actual & ~predicted).sum())
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and (precision + recall) else None
    return {
        "spike_threshold": float(threshold),
        "precision": float(precision) if precision is not None else None,
        "recall": float(recall) if recall is not None else None,
        "f1": float(f1) if f1 is not None else None,
        "false_positive_count": fp,
        "false_negative_count": fn,
        "true_positive_count": tp,
    }


def hourly_metrics(frame: pd.DataFrame, prediction: pd.Series, target_field: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if "hour" in frame.columns:
        hours = pd.to_numeric(frame["hour"], errors="coerce")
    else:
        hours = pd.to_datetime(frame[TIME_FIELD], errors="coerce").dt.hour
    for hour in range(24):
        mask = hours == hour
        metrics = regression_metrics(frame.loc[mask, target_field], prediction.loc[mask])
        rows.append({"hour": hour, "mae": metrics["mae"], "rmse": metrics["rmse"], "sample_count": metrics["sample_count"]})
    return rows


def _time_range(frame: pd.DataFrame, time_field: str) -> dict[str, Any]:
    return {
        "start": frame[time_field].min() if time_field in frame.columns and not frame.empty else None,
        "end": frame[time_field].max() if time_field in frame.columns and not frame.empty else None,
    }


def evaluate_model_on_split(
    split_name: str,
    frame: pd.DataFrame,
    model_name: str,
    prediction: pd.Series,
    config: BacktestRunnerConfig,
    spike_threshold: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    target = frame[config.target_field]
    peak_mask = _numeric_default(frame, "is_peak_hour").fillna(0).astype(int).eq(1)
    extreme_mask = _numeric_default(frame, "is_extreme_weather").fillna(0).astype(int).eq(1)
    overall = regression_metrics(target, prediction)
    peak = regression_metrics(target.loc[peak_mask], prediction.loc[peak_mask])
    extreme = regression_metrics(target.loc[extreme_mask], prediction.loc[extreme_mask])
    spike = spike_metrics(target, prediction, spike_threshold)
    result = {
        "split": split_name,
        "model": model_name,
        "time_range": _time_range(frame, config.time_field),
        "overall": {
            "mae": overall["mae"],
            "rmse": overall["rmse"],
            "mape": overall["mape"],
            "r2": overall["r2"],
            "sample_count": overall["sample_count"],
        },
        "peak": {
            "peak_hour_mae": peak["mae"],
            "peak_hour_rmse": peak["rmse"],
            "peak_hour_bias": peak["bias"],
            "peak_hour_sample_count": peak["sample_count"],
        },
        "spike": spike,
        "extreme_weather": {
            "definition": "is_extreme_weather=1 from shifted rolling temperature quantiles",
            "extreme_weather_mae": extreme["mae"],
            "extreme_weather_rmse": extreme["rmse"],
            "sample_count": extreme["sample_count"],
        },
        "hourly": hourly_metrics(frame, prediction, config.target_field),
    }
    prediction_frame = pd.DataFrame(
        {
            "split": split_name,
            "datetime": frame[config.time_field],
            "model": model_name,
            "actual": pd.to_numeric(target, errors="coerce"),
            "prediction": pd.to_numeric(prediction, errors="coerce"),
            "is_peak_hour": _numeric_default(frame, "is_peak_hour").fillna(0).astype(int),
            "is_extreme_weather": _numeric_default(frame, "is_extreme_weather").fillna(0).astype(int),
        }
    )
    prediction_frame["is_spike_actual"] = prediction_frame["actual"] >= spike_threshold
    prediction_frame["is_spike_predicted"] = prediction_frame["prediction"] >= spike_threshold
    return result, prediction_frame


def _compare_to_reference(metrics: list[dict[str, Any]], reference_model: str = "persistence_24h") -> list[dict[str, Any]]:
    by_key = {(row["split"], row["model"]): row for row in metrics}
    comparisons: list[dict[str, Any]] = []
    for row in metrics:
        if row["model"] == reference_model:
            continue
        ref = by_key.get((row["split"], reference_model))
        if not ref:
            continue
        row_rmse = row["overall"]["rmse"]
        ref_rmse = ref["overall"]["rmse"]
        comparisons.append(
            {
                "split": row["split"],
                "model": row["model"],
                "reference_model": reference_model,
                "overall_rmse_delta": None if row_rmse is None or ref_rmse is None else float(row_rmse - ref_rmse),
                "overall_mae_delta": None
                if row["overall"]["mae"] is None or ref["overall"]["mae"] is None
                else float(row["overall"]["mae"] - ref["overall"]["mae"]),
                "is_better_than_reference_overall_rmse": bool(row_rmse < ref_rmse) if row_rmse is not None and ref_rmse is not None else None,
            }
        )
    return comparisons


def _render_report(metrics_payload: dict[str, Any]) -> str:
    lines = [
        "# P2 Backtest Report",
        "",
        f"- created_at: {metrics_payload['created_at']}",
        f"- acceptable_for_backtest: {metrics_payload['acceptable_for_backtest']}",
        f"- leakage_high_risk_count: {metrics_payload['leakage_check']['high_risk_count']}",
        f"- spike_threshold: {metrics_payload['spike_threshold']}",
        "",
        "## Baseline Methods",
        "",
    ]
    for name, desc in metrics_payload["baseline_methods"].items():
        lines.append(f"- {name}: {desc}")
    if metrics_payload.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        for warning in metrics_payload["warnings"]:
            lines.append(f"- {warning}")
    lines.extend(["", "## Overall Metrics", ""])
    for item in metrics_payload["metrics"]:
        overall = item["overall"]
        lines.append(
            f"- {item['split']} / {item['model']}: rows={overall['sample_count']}, "
            f"MAE={overall['mae']}, RMSE={overall['rmse']}, MAPE={overall['mape']}, R2={overall['r2']}"
        )
    lines.extend(["", "## Baseline Comparison", ""])
    if not metrics_payload["baseline_comparisons"]:
        lines.append("- No model comparison available beyond the reference baseline.")
    else:
        for item in metrics_payload["baseline_comparisons"]:
            lines.append(
                f"- {item['split']} / {item['model']} vs {item['reference_model']}: "
                f"RMSE delta={item['overall_rmse_delta']}, better={item['is_better_than_reference_overall_rmse']}"
            )
    lines.extend(["", "## Scenario Notes", ""])
    lines.append("- 后续模型优化必须同时对比 overall、peak、spike、extreme_weather 和 per-hour 指标。")
    lines.append("- 当前报告仅建立可复现 baseline/backtest，不代表模型调参或模型替换。")
    lines.append("")
    return "\n".join(lines)


def run_backtest(config: BacktestRunnerConfig | None = None) -> dict[str, Any]:
    cfg = config or BacktestRunnerConfig()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    splits = load_dataset_splits(cfg.dataset_dir)
    feature_schema = load_feature_schema(cfg.dataset_dir)
    schema_checks = {
        name: validate_feature_frame_schema(frame, feature_schema, allow_extra=True)
        for name, frame in splits.items()
    }
    if not all(item["ok"] for item in schema_checks.values()):
        raise RuntimeError(f"feature schema mismatch: {schema_checks}")

    leakage = run_leakage_check(LeakageCheckConfig(dataset_dir=cfg.dataset_dir, output_dir=cfg.output_dir))
    if cfg.fail_on_high_risk_leakage and not leakage["acceptable_for_backtest"]:
        raise RuntimeError(f"high-risk leakage detected: {leakage['issues']}")

    train_target = pd.to_numeric(splits["train"][cfg.target_field], errors="coerce").dropna()
    if train_target.empty:
        raise ValueError("train split has no valid target values.")
    spike_threshold = float(train_target.quantile(cfg.spike_quantile))

    metrics: list[dict[str, Any]] = []
    prediction_frames: list[pd.DataFrame] = []
    warnings: list[str] = []
    for split_name in ["validation", "test"]:
        frame = splits[split_name]
        predictions = _baseline_predictions(frame)
        if cfg.include_legacy:
            legacy_pred, warning = _legacy_predictions(frame, feature_schema)
            if warning:
                warnings.append(f"{split_name}: {warning}")
            elif legacy_pred is not None:
                predictions["legacy_active_model"] = legacy_pred
        for model_name, prediction in predictions.items():
            result, prediction_frame = evaluate_model_on_split(split_name, frame, model_name, prediction, cfg, spike_threshold)
            metrics.append(result)
            prediction_frames.append(prediction_frame)

    baseline_methods = {
        "persistence_24h": "使用前一天同小时价格 da_price_lag_24 作为预测。",
        "rolling_same_hour_7d": "使用过去 7 天同小时价格均值作为预测。",
        "legacy_active_model": "可选包装 model_ops.active_model_loader 的当前 active legacy 模型；不可用时只记录 warning。",
    }
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "config": {**asdict(cfg), "dataset_dir": str(cfg.dataset_dir), "output_dir": str(cfg.output_dir)},
        "acceptable_for_backtest": bool(leakage["acceptable_for_backtest"]),
        "spike_threshold": spike_threshold,
        "baseline_methods": baseline_methods,
        "schema_checks": schema_checks,
        "leakage_check": leakage,
        "metrics": metrics,
        "baseline_comparisons": _compare_to_reference(metrics, "persistence_24h"),
        "warnings": warnings,
    }

    predictions = pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame()
    metrics_path = cfg.output_dir / "metrics.json"
    report_path = cfg.output_dir / "backtest_report.md"
    predictions_path = cfg.output_dir / "backtest_predictions.csv"
    _write_json(metrics_path, payload)
    report_path.write_text(_render_report(payload), encoding="utf-8")
    predictions.to_csv(predictions_path, index=False, encoding="utf-8-sig")
    payload["output_paths"] = {
        "metrics": str(metrics_path),
        "backtest_report": str(report_path),
        "backtest_predictions": str(predictions_path),
    }
    _write_json(metrics_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run P2 reproducible baseline backtest.")
    parser.add_argument("--dataset-dir", default="output/p2")
    parser.add_argument("--output-dir", default="output/p2")
    parser.add_argument("--spike-quantile", type=float, default=0.95)
    parser.add_argument("--skip-legacy", action="store_true")
    parser.add_argument("--fail-on-high-risk-leakage", action="store_true")
    args = parser.parse_args()
    result = run_backtest(
        BacktestRunnerConfig(
            dataset_dir=Path(args.dataset_dir),
            output_dir=Path(args.output_dir),
            spike_quantile=args.spike_quantile,
            include_legacy=not args.skip_legacy,
            fail_on_high_risk_leakage=args.fail_on_high_risk_leakage,
        )
    )
    print(json.dumps(_sanitize_json({"output_paths": result["output_paths"], "acceptable_for_backtest": result["acceptable_for_backtest"]}), ensure_ascii=False, indent=2, default=_json_default, allow_nan=False))


if __name__ == "__main__":
    main()

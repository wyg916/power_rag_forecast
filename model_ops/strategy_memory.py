from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from database_utils import apply_database_migrations, create_database_engine, get_database_config
from model_ops.model_registry import load_artifact_manifest


def _log(log, message: str) -> None:
    if log:
        log(message)


def _metric_row(metrics: dict[str, Any]) -> dict[str, Any]:
    rows = metrics.get("metrics") or []
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    if "RMSE" in df.columns:
        preferred = df[df.get("模型", "").astype(str).str.contains("融合|增强", regex=True, na=False)] if "模型" in df.columns else pd.DataFrame()
        if not preferred.empty:
            return preferred.iloc[0].to_dict()
        return df.sort_values("RMSE").iloc[0].to_dict()
    return dict(rows[0])


def _peak_row(metrics: dict[str, Any]) -> dict[str, Any]:
    rows = metrics.get("peak_spike_metrics") or []
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    if "模型" in df.columns:
        preferred = df[df["模型"].astype(str).str.contains("融合|增强", regex=True, na=False)]
        if not preferred.empty:
            return preferred.iloc[0].to_dict()
    return df.iloc[0].to_dict()


def _find(row: dict[str, Any], contains: list[str]) -> Any:
    for key, value in row.items():
        text = str(key)
        if all(part in text for part in contains):
            return value
    return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def register_strategy_result(config: dict[str, Any], artifact_dir: str | Path, log=None) -> str | None:
    if not get_database_config(config).enabled:
        _log(log, "WARNING: 数据库未启用，跳过 model_strategy_memory 登记。")
        return None
    path = Path(artifact_dir)
    try:
        manifest = load_artifact_manifest(path)
        metrics_path = path / "metrics.json"
        training_path = path / "training_config.json"
        metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
        training = json.loads(training_path.read_text(encoding="utf-8")) if training_path.exists() else {}
    except Exception as exc:
        _log(log, f"WARNING: 读取模型策略产物失败，跳过策略记忆登记：{exc}")
        return None

    metric = _metric_row(metrics)
    peak = _peak_row(metrics)
    datasets = training.get("datasets") or []
    train_days = None
    try:
        train = next((item for item in datasets if item.get("name") == "train"), None)
        if train and train.get("start_datetime") and train.get("end_datetime"):
            train_days = int((pd.to_datetime(train["end_datetime"]) - pd.to_datetime(train["start_datetime"])).days)
    except Exception:
        train_days = None

    model_version = str(manifest.get("model_version") or path.name)
    feature_version = training.get("feature_version")
    rmse = _safe_float(metric.get("RMSE"))
    mae = _safe_float(metric.get("MAE"))
    peak_rmse = _safe_float(_find(peak, ["高峰", "RMSE"]))
    spike_rmse = _safe_float(_find(peak, ["尖峰", "RMSE"]))
    stability_score = None
    if rmse is not None:
        stability_score = float(1.0 / (1.0 + rmse + (peak_rmse or 0) * 0.25 + (spike_rmse or 0) * 0.25))
    strategy_payload = f"{model_version}|{feature_version}|{metrics.get('base_model_name')}|{metrics.get('peak_model_name')}|{metrics.get('best_alpha')}|{metrics.get('best_peak_floor')}"
    strategy_id = "strategy_" + hashlib.sha256(strategy_payload.encode("utf-8")).hexdigest()[:16]

    apply_database_migrations(config, log=log)
    engine = create_database_engine(config)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO model_strategy_memory (
                    strategy_id, model_version, feature_set_version, model_type,
                    training_window_days, alpha, peak_floor, mae, rmse,
                    peak_rmse, spike_rmse, stability_score, is_recommended, created_at
                )
                VALUES (
                    :strategy_id, :model_version, :feature_set_version, :model_type,
                    :training_window_days, :alpha, :peak_floor, :mae, :rmse,
                    :peak_rmse, :spike_rmse, :stability_score, :is_recommended, CURRENT_TIMESTAMP
                )
                ON DUPLICATE KEY UPDATE
                    mae = VALUES(mae),
                    rmse = VALUES(rmse),
                    peak_rmse = VALUES(peak_rmse),
                    spike_rmse = VALUES(spike_rmse),
                    stability_score = VALUES(stability_score),
                    is_recommended = VALUES(is_recommended)
                """
            ),
            {
                "strategy_id": strategy_id,
                "model_version": model_version,
                "feature_set_version": feature_version,
                "model_type": str(metrics.get("base_model_name") or "") + " + " + str(metrics.get("peak_model_name") or ""),
                "training_window_days": train_days,
                "alpha": _safe_float(metrics.get("best_alpha")),
                "peak_floor": _safe_float(metrics.get("best_peak_floor")),
                "mae": mae,
                "rmse": rmse,
                "peak_rmse": peak_rmse,
                "spike_rmse": spike_rmse,
                "stability_score": stability_score,
                "is_recommended": 0,
            },
        )
    _log(log, f"SUCCESS: 模型策略记忆已登记：{strategy_id}")
    return strategy_id


def rank_strategies(config: dict[str, Any], limit: int = 20) -> pd.DataFrame:
    if not get_database_config(config).enabled:
        return pd.DataFrame()
    apply_database_migrations(config)
    engine = create_database_engine(config)
    with engine.connect() as conn:
        return pd.read_sql(
            text(
                """
                SELECT *
                FROM model_strategy_memory
                ORDER BY is_recommended DESC, stability_score DESC, rmse ASC, peak_rmse ASC, spike_rmse ASC
                LIMIT :limit
                """
            ),
            conn,
            params={"limit": int(limit)},
        )


def get_recommended_strategy(config: dict[str, Any]) -> dict[str, Any]:
    ranked = rank_strategies(config, limit=1)
    return {} if ranked.empty else ranked.iloc[0].to_dict()


def summarize_strategy_memory(config: dict[str, Any]) -> dict[str, Any]:
    ranked = rank_strategies(config, limit=50)
    if ranked.empty:
        return {"strategy_count": 0, "recommended_strategy": {}, "status": "empty"}
    return {
        "strategy_count": int(len(ranked)),
        "recommended_strategy": ranked.iloc[0].to_dict(),
        "best_rmse": _safe_float(ranked["rmse"].min()) if "rmse" in ranked.columns else None,
        "status": "available",
    }

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from sqlalchemy import text

from database_utils import apply_database_migrations, create_database_engine, get_database_config


@dataclass
class ModelHealthDecision:
    status: str
    reason: str
    should_retrain: bool
    metrics: dict[str, float]


def summarize_error_window(df: pd.DataFrame) -> dict[str, float]:
    if df is None or df.empty:
        return {"sample_count": 0.0, "mae": 0.0, "rmse": 0.0, "mape": 0.0}
    return {
        "sample_count": float(len(df)),
        "mae": float(pd.to_numeric(df["abs_error"], errors="coerce").mean()),
        "rmse": float(((pd.to_numeric(df["actual_price"], errors="coerce") - pd.to_numeric(df["predicted_price"], errors="coerce")) ** 2).mean() ** 0.5),
        "mape": float(pd.to_numeric(df["pct_error"], errors="coerce").mean()),
    }


def decide_retrain(recent: dict[str, float], baseline: dict[str, float], min_samples: int = 24) -> ModelHealthDecision:
    if recent.get("sample_count", 0) < min_samples:
        return ModelHealthDecision("insufficient_data", "近期已回填样本不足，暂不触发重训。", False, recent)
    recent_rmse = float(recent.get("rmse") or 0)
    baseline_rmse = float(baseline.get("rmse") or 0)
    if baseline_rmse > 0 and recent_rmse > baseline_rmse * 1.2:
        return ModelHealthDecision("degraded", "最近窗口 RMSE 较基线升高超过 20%，建议训练候选模型。", True, recent)
    if recent_rmse > 80:
        return ModelHealthDecision("high_error", "最近窗口 RMSE 超过硬阈值 80，建议训练候选模型。", True, recent)
    return ModelHealthDecision("healthy", "模型近期误差未触发重训阈值。", False, recent)


def evaluate_model_health(config: dict[str, Any], recent_days: int = 7, baseline_days: int = 30, log=None) -> ModelHealthDecision:
    if not get_database_config(config).enabled:
        return ModelHealthDecision("database_disabled", "数据库未启用，无法评估模型误差漂移。", False, {})

    apply_database_migrations(config, log=log)
    engine = create_database_engine(config)
    with engine.connect() as conn:
        recent_df = pd.read_sql(
            text(
                """
                SELECT predicted_price, actual_price, abs_error, pct_error
                FROM prediction_tracking
                WHERE actual_price IS NOT NULL
                  AND forecast_datetime >= DATE_SUB(NOW(), INTERVAL :recent_days DAY)
                """
            ),
            conn,
            params={"recent_days": int(recent_days)},
        )
        baseline_df = pd.read_sql(
            text(
                """
                SELECT predicted_price, actual_price, abs_error, pct_error
                FROM prediction_tracking
                WHERE actual_price IS NOT NULL
                  AND forecast_datetime >= DATE_SUB(NOW(), INTERVAL :baseline_days DAY)
                """
            ),
            conn,
            params={"baseline_days": int(baseline_days)},
        )
    decision = decide_retrain(summarize_error_window(recent_df), summarize_error_window(baseline_df))
    if log:
        log(f"模型健康状态：{decision.status}，{decision.reason}")
    return decision

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from sqlalchemy import text

from backend.app.services.model_fact_service import DEFAULT_MODEL_DOMAIN, DEFAULT_TARGET_NAME, ModelFactService
from database_utils import create_database_engine, get_database_config
from model_ops.strategy_memory import get_recommended_strategy


@dataclass
class RetrainPolicyDecision:
    should_retrain: bool
    retrain_reason: str
    recommended_strategy: dict[str, Any]
    degradation_metrics: dict[str, Any]


def _empty(reason: str) -> RetrainPolicyDecision:
    return RetrainPolicyDecision(False, reason, {}, {})


def check_model_degradation(config: dict[str, Any], log=None) -> RetrainPolicyDecision:
    if not get_database_config(config).enabled:
        return _empty("数据库未启用，无法执行自动重训判断。")
    engine = create_database_engine(config)
    with engine.connect() as conn:
        perf = pd.read_sql(
            text(
                """
                SELECT *
                FROM model_performance_daily
                ORDER BY metric_date DESC
                LIMIT 60
                """
            ),
            conn,
        )
    model_cfg = config.get("model_learning", {}) or {}
    domain = str(model_cfg.get("domain") or DEFAULT_MODEL_DOMAIN).strip().lower()
    target_name = str(model_cfg.get("target_name") or DEFAULT_TARGET_NAME).strip()
    active = ModelFactService(engine).get_active_model(domain, target_name)

    if perf.empty:
        return _empty("暂无可用 model_performance_daily 误差样本，暂不重训。")
    perf["metric_date"] = pd.to_datetime(perf["metric_date"], errors="coerce")
    now = pd.Timestamp.now().normalize()
    recent7 = perf[perf["metric_date"] >= now - pd.Timedelta(days=7)]
    recent30 = perf[perf["metric_date"] >= now - pd.Timedelta(days=30)]
    metrics: dict[str, Any] = {
        "recent7_samples": int(pd.to_numeric(recent7.get("sample_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()),
        "recent30_samples": int(pd.to_numeric(recent30.get("sample_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()),
        "recent7_rmse": float(pd.to_numeric(recent7.get("rmse", pd.Series(dtype=float)), errors="coerce").mean()) if not recent7.empty else None,
        "recent30_rmse": float(pd.to_numeric(recent30.get("rmse", pd.Series(dtype=float)), errors="coerce").mean()) if not recent30.empty else None,
        "recent_peak_rmse": float(pd.to_numeric(recent7.get("peak_rmse", pd.Series(dtype=float)), errors="coerce").mean()) if not recent7.empty else None,
        "recent_spike_rmse": float(pd.to_numeric(recent7.get("spike_rmse", pd.Series(dtype=float)), errors="coerce").mean()) if not recent7.empty else None,
        "data_drift_score": 0.0,
    }
    reasons: list[str] = []
    if metrics["recent7_rmse"] and metrics["recent30_rmse"] and metrics["recent7_rmse"] > metrics["recent30_rmse"] * 1.2:
        reasons.append("最近7天 RMSE 较最近30天升高超过 20%")
    if not recent7.empty and "peak_rmse" in recent7.columns:
        high_peak_days = pd.to_numeric(recent7["peak_rmse"], errors="coerce").fillna(0) > 35
        if int(high_peak_days.tail(3).sum()) >= 3:
            reasons.append("高峰 RMSE 连续3天高于阈值")
    if active and active.get("spike_rmse") and metrics["recent_spike_rmse"]:
        if metrics["recent_spike_rmse"] > float(active["spike_rmse"]) * 1.15:
            reasons.append("尖峰 RMSE 高于 active 历史均值 15%")
    if metrics["data_drift_score"] > 0.35:
        reasons.append("数据漂移评分超过阈值")
    if active:
        last_train = pd.to_datetime(active.get("created_at") or active.get("activated_at"), errors="coerce")
        if pd.notna(last_train):
            days_since_train = int((pd.Timestamp.now() - last_train).days)
            metrics["days_since_last_retrain"] = days_since_train
            if days_since_train > 14:
                reasons.append("距离上次完整重训超过 14 天")
    else:
        reasons.append("当前没有 Active 模型")

    recommended_strategy = get_recommended_strategy(config)
    decision = RetrainPolicyDecision(
        should_retrain=bool(reasons),
        retrain_reason="；".join(reasons) if reasons else "模型近期表现未触发重训阈值。",
        recommended_strategy=recommended_strategy,
        degradation_metrics=metrics,
    )
    if log:
        log(f"自动重训判断：{decision.retrain_reason}")
    return decision


def should_retrain(config: dict[str, Any], log=None) -> bool:
    return check_model_degradation(config, log=log).should_retrain


def build_retrain_reason(config: dict[str, Any], log=None) -> str:
    return check_model_degradation(config, log=log).retrain_reason


def select_retrain_strategy(config: dict[str, Any]) -> dict[str, Any]:
    return check_model_degradation(config).recommended_strategy

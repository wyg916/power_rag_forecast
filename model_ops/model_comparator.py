from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from sqlalchemy import text

from database_utils import apply_database_migrations, create_database_engine, get_database_config, now_text


@dataclass
class ComparisonDecision:
    decision: str
    reason: str
    promote: bool
    candidate_model_version: str = ""
    active_model_version: str = ""


def compare_candidate_to_active(candidate: dict[str, float], active: dict[str, float]) -> ComparisonDecision:
    candidate_rmse = float(candidate.get("rmse") or candidate.get("test_rmse") or 0)
    active_rmse = float(active.get("rmse") or active.get("test_rmse") or 0)
    candidate_peak = float(candidate.get("peak_rmse") or 0)
    active_peak = float(active.get("peak_rmse") or 0)
    candidate_spike = float(candidate.get("spike_rmse") or 0)
    active_spike = float(active.get("spike_rmse") or 0)

    if active_rmse <= 0:
        return ComparisonDecision("manual_review", "当前 active 模型缺少可比 RMSE，需人工确认。", False)
    if candidate_rmse <= active_rmse * 0.97 and (not active_peak or candidate_peak <= active_peak) and (not active_spike or candidate_spike <= active_spike * 1.05):
        return ComparisonDecision("promote", "候选模型满足整体、高峰和尖峰上线阈值。", True)
    return ComparisonDecision("keep_candidate", "候选模型未达到自动上线阈值，保留为 candidate。", False)


def compare_latest_candidate(config: dict[str, Any], log=None) -> ComparisonDecision:
    if not get_database_config(config).enabled:
        return ComparisonDecision("database_disabled", "数据库未启用，无法执行模型对比。", False)

    apply_database_migrations(config, log=log)
    engine = create_database_engine(config)
    with engine.begin() as conn:
        candidate = conn.execute(
            text(
                """
                SELECT model_version, test_rmse, peak_rmse, spike_rmse
                FROM model_registry
                WHERE status = 'candidate'
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
        ).mappings().fetchone()
        active = conn.execute(
            text(
                """
                SELECT model_version, test_rmse, peak_rmse, spike_rmse
                FROM model_registry
                WHERE is_active = 1
                ORDER BY activated_at DESC, created_at DESC
                LIMIT 1
                """
            )
        ).mappings().fetchone()
        if not candidate or not active:
            return ComparisonDecision("insufficient_models", "缺少 candidate 或 active 模型，无法自动对比。", False)

        decision = compare_candidate_to_active(dict(candidate), dict(active))
        decision.candidate_model_version = str(candidate["model_version"])
        decision.active_model_version = str(active["model_version"])
        conn.execute(
            text(
                """
                INSERT INTO model_comparison_runs (
                    comparison_id, candidate_model_version, active_model_version,
                    decision, reason, created_at
                )
                VALUES (:comparison_id, :candidate, :active, :decision, :reason, CURRENT_TIMESTAMP)
                """
            ),
            {
                "comparison_id": "comparison_" + now_text("%Y%m%d_%H%M%S"),
                "candidate": candidate["model_version"],
                "active": active["model_version"],
                "decision": decision.decision,
                "reason": decision.reason,
            },
        )
    if log:
        log(f"模型对比结果：{decision.decision}，{decision.reason}")
    return decision

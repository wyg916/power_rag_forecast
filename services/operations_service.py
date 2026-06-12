from __future__ import annotations

from typing import Any, Callable

from model_ops.actuals_updater import update_actuals_and_errors
from model_ops.auto_retrain_policy import check_model_degradation
from model_ops.error_memory import update_error_memory
from model_ops.model_comparator import compare_latest_candidate
from model_ops.model_monitor import evaluate_model_health
from model_ops.promotion_manager import promote_to_active
from model_ops.retrain_scheduler import create_retrain_job
from services.prediction_service import run_prediction


LogFunc = Callable[[str], None] | None


def run_model_ops_daily(config: dict[str, Any], log: LogFunc = None) -> dict[str, Any]:
    """每日模型运维任务：真实值回填、误差统计、健康判断、必要时登记重训。"""

    actuals_result = update_actuals_and_errors(config, log=log)
    health = evaluate_model_health(config, log=log)
    job_id = None
    if health.should_retrain:
        job_id = create_retrain_job(config, trigger_reason=health.reason, trigger_source="model_monitor", log=log)
    return {
        "actuals": actuals_result.__dict__,
        "health": health.__dict__,
        "retrain_job_id": job_id,
    }


def run_model_auto_optimize(
    config: dict[str, Any],
    run_context: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    log: LogFunc = None,
) -> dict[str, Any]:
    """执行误差记忆、退化判断、必要时重训和候选模型对比上线。"""

    actuals_result = update_actuals_and_errors(config, log=log)
    memory_rows = update_error_memory(config, log=log)
    decision = check_model_degradation(config, log=log)
    retrain_result: dict[str, Any] | None = None
    comparison_result: dict[str, Any] | None = None
    promoted = False

    if decision.should_retrain:
        if log:
            log(f"自动优化触发候选模型重训：{decision.retrain_reason}")
        create_retrain_job(config, trigger_reason=decision.retrain_reason, trigger_source="model_auto_optimize", status="running", log=log)
        result = run_prediction(config=config, run_context=run_context, log=log, env=env, fast_forecast=False)
        retrain_result = result.__dict__
        comparison = compare_latest_candidate(config, log=log)
        comparison_result = comparison.__dict__
        if comparison.promote and getattr(comparison, "candidate_model_version", ""):
            promoted = promote_to_active(config, comparison.candidate_model_version, approved_by="model_auto_optimize", log=log)
    elif log:
        log("模型误差未触发重训阈值，本次自动优化不重训。")

    return {
        "actuals": actuals_result.__dict__,
        "error_memory_rows": memory_rows,
        "policy": decision.__dict__,
        "retrain_result": retrain_result,
        "comparison": comparison_result,
        "promoted": promoted,
    }

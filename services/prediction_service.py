from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from automation_common import format_duration, get_pipeline_paths, get_run_context, load_config, setup_run_logger
from database_utils import export_prediction_inputs_from_database, save_pipeline_event, sync_result_tables_to_database
from model_ops.model_registry import register_model_artifact
from model_ops.prediction_tracker import build_prediction_tracking_frame, track_future_prediction_file, write_prediction_tracking
from model_ops.strategy_memory import register_strategy_result
from prediction_engine.fast_forecast import forecast_with_saved_model
from prediction_engine.pipeline import run_prediction_engine


LogFunc = Callable[[str], None] | None


@dataclass
class PredictionRunResult:
    engine_script: Path
    result_table_dir: Path
    elapsed: str
    returncode: int


def _is_fast_mode(env: Mapping[str, str] | None, explicit: bool) -> bool:
    return explicit or bool(env and str(env.get("PIPELINE_FORECAST_MODE", "")).strip().lower() == "fast")


def _write_fast_prediction_tracking(config: dict[str, Any], result, context: dict[str, Any], log: LogFunc = None) -> None:
    if not result.future_result_path.exists():
        return
    future_result = pd.read_excel(result.future_result_path, engine="openpyxl")
    tracking_df = build_prediction_tracking_frame(
        future_result,
        run_id=context["run_id"],
        model_version=result.model_version,
        feature_version=result.feature_version,
    )
    write_prediction_tracking(config, tracking_df, run_id=context["run_id"], log=log)


def _run_fast_forecast(config: dict[str, Any], context: dict[str, Any], paths, log: LogFunc = None) -> PredictionRunResult:
    start = time.perf_counter()
    if log:
        log("启用快速预测模式：加载 Active 模型，不重新训练。")
    result = forecast_with_saved_model(config, run_context=context, log=log)
    elapsed = format_duration(time.perf_counter() - start)
    if log:
        log(f"Active 模型快速预测完成，耗时：{elapsed}。")
    save_pipeline_event(config, "fast_forecast", "completed", f"Active 模型快速预测完成，记录数：{result.rows}", context)

    if log:
        log("同步快速预测结果数据表到数据库。")
    sync_result_tables_to_database(
        paths.result_table_dir,
        config,
        run_context=context,
        log=log,
        filenames=[
            "18_未来24小时预测结果_正式版.xlsx",
            "18_未来24小时预测输入特征_正式版.xlsx",
            "19_业务统计摘要.xlsx",
        ],
    )
    save_pipeline_event(config, "prediction_results_sync", "completed", "快速预测结果数据表已同步到数据库", context)
    _write_fast_prediction_tracking(config, result, context, log=log)
    return PredictionRunResult(paths.engine_script, paths.result_table_dir, elapsed, 0)


def run_prediction(
    config: dict[str, Any] | None = None,
    run_context: dict[str, Any] | None = None,
    log: LogFunc = None,
    env: Mapping[str, str] | None = None,
    fast_forecast: bool = False,
) -> PredictionRunResult:
    config = config or load_config()
    paths = get_pipeline_paths(config)
    context = run_context or get_run_context()
    if log is None:
        log, _ = setup_run_logger(paths.log_dir, "01_run_prediction")

    if not paths.engine_script.exists():
        raise FileNotFoundError(f"未找到预测引擎脚本：{paths.engine_script}")

    log("通过 prediction_service 导出预测输入数据。")
    export_prediction_inputs_from_database(paths.data_dir, config, log=log)
    save_pipeline_event(config, "prediction_input_export", "completed", "已从数据库导出预测输入", context)

    if _is_fast_mode(env, fast_forecast):
        return _run_fast_forecast(config, context, paths, log=log)

    start = time.perf_counter()
    log(f"通过 prediction_engine.pipeline 执行完整训练预测引擎：{paths.engine_script.name}")
    completed = run_prediction_engine(paths.engine_script, cwd=paths.root_dir, env=env)
    if completed.returncode != 0:
        save_pipeline_event(config, "prediction_engine", "failed", f"返回码：{completed.returncode}", context)
        raise SystemExit(completed.returncode)

    elapsed = format_duration(time.perf_counter() - start)
    log(f"预测引擎执行完成，耗时：{elapsed}。")
    save_pipeline_event(config, "prediction_engine", "completed", f"预测引擎执行完成，耗时：{elapsed}", context)

    log("同步预测结果数据表到数据库。")
    sync_result_tables_to_database(paths.result_table_dir, config, run_context=context, log=log)
    save_pipeline_event(config, "prediction_results_sync", "completed", "预测结果数据表已同步到数据库", context)

    artifact_dir = paths.root_dir / "model_artifacts" / f"model_{context['run_id']}"
    future_result_path = paths.result_table_dir / "18_未来24小时预测结果_正式版.xlsx"
    if artifact_dir.exists():
        try:
            model_version = register_model_artifact(config, artifact_dir, status="candidate")
            log(f"模型 artifact 已登记为 candidate：{model_version}")
            register_strategy_result(config, artifact_dir, log=log)
            if future_result_path.exists():
                track_future_prediction_file(config, future_result_path, artifact_dir, context["run_id"], log=log)
        except Exception as exc:
            log(f"模型注册、策略记忆或预测追踪写入失败，不影响主流程：{exc}")
    else:
        log(f"未发现本次模型 artifact 目录，跳过模型注册：{artifact_dir}")

    return PredictionRunResult(paths.engine_script, paths.result_table_dir, elapsed, completed.returncode)

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd
from sqlalchemy import text

from backend.app.config import PROJECT_ROOT, project_paths
from backend.app.data_access import load_latest_forecast
from backend.app.repositories.base import dumps_json, postgres_engine
from backend.app.repositories.task_repository import task_overview
from backend.app.services.core_data_sync import sync_core_facts_and_tariff_assets
from backend.app.services.forecast_transaction_service import (
    ForecastRunRequest,
    ForecastTransactionError,
    ForecastTransactionService,
    PredictionBatch,
    generate_run_id,
)
from model_ops.result_hash import RESULT_VALUE_COLUMNS


class TaskStepLogger(Protocol):
    def log(self, step: str, message: str, *, level: str = "info", progress: float | None = None, metadata: dict[str, Any] | None = None) -> None:
        ...


def _safe_horizon(value: Any, default: int = 24) -> int:
    try:
        return max(1, min(168, int(value or default)))
    except Exception:
        return default


def _write_backend_forecast(payload: dict[str, Any], context: TaskStepLogger | None) -> dict[str, Any]:
    raise RuntimeError(
        "合成预测回退已禁用；必须使用已验证 Active artifact、170 项输入契约和 T003 原子事务链。"
    )


def run_price_predict(payload: dict[str, Any], context: TaskStepLogger | None = None) -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL 不可用，无法启动预测事务。")
    service = ForecastTransactionService(engine)
    run_id = generate_run_id()
    active = service.active_model("price", "da_price")
    input_path = project_paths().result_table_dir / "18_未来24小时预测输入特征_正式版.xlsx"
    if not input_path.exists():
        raise RuntimeError("严格 24×170 预测输入不存在；未创建 forecast run。")
    artifact_path = Path(str(active.get("artifact_path") or "")).resolve(strict=True)
    isolated_python = PROJECT_ROOT / ".codex_envs" / "t002_sklearn160" / "Scripts" / "python.exe"
    if not isolated_python.exists():
        raise RuntimeError("T002 隔离推理环境不存在；未创建 forecast run。")
    output_dir = PROJECT_ROOT / ".codex_tmp" / "t003_runtime" / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    temp_dir = PROJECT_ROOT / ".codex_tmp" / "task_runtime_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    if context:
        context.log("parse", "创建统一预测 run_id", progress=18, metadata={"run_id": run_id})
        context.log("load_data", "使用唯一 Active 模型与 T002 隔离环境", progress=36)
    child_env = dict(os.environ)
    child_env.update(
        {
            "TEMP": str(temp_dir),
            "TMP": str(temp_dir),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": str(PROJECT_ROOT),
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "VECLIB_MAXIMUM_THREADS": "1",
            "PYTHONHASHSEED": "0",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "ALL_PROXY": "",
            "NO_PROXY": "*",
            "T003_OPENPYXL_SITE_PACKAGES": str(PROJECT_ROOT / ".venv" / "Lib" / "site-packages"),
        }
    )
    child_env.pop("DATABASE_URL", None)
    try:
        completed = subprocess.run(
            [
                str(isolated_python),
                str(PROJECT_ROOT / "scripts" / "t003_isolated_inference.py"),
                "--artifact",
                str(artifact_path),
                "--input",
                str(input_path),
                "--output",
                str(output_dir),
            ],
            cwd=str(PROJECT_ROOT),
            env=child_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            check=False,
        )
        if completed.returncode != 0:
            raise ForecastTransactionError("MODEL_INFERENCE_FAILED", "隔离模型推理失败")
        manifest = json.loads((output_dir / "prediction_manifest.json").read_text(encoding="utf-8"))
        timestamps = pd.DatetimeIndex(
            pd.to_datetime(
                json.loads((output_dir / "prediction_timestamps.json").read_text(encoding="utf-8")),
                utc=True,
            )
        ).tz_convert("America/New_York")
        values = pd.DataFrame(
            np.load(output_dir / "prediction_values.npy", allow_pickle=False),
            columns=list(RESULT_VALUE_COLUMNS),
        )
        batch = PredictionBatch(timestamps, values)
        request = ForecastRunRequest(
            domain="price",
            target_name="da_price",
            input_start_at=timestamps[0].to_pydatetime(),
            input_end_at=timestamps[-1].to_pydatetime(),
            input_hash=str(manifest["input_file_hash"]),
            environment_hash=str(manifest["environment_hash"]),
            source_type="t003_isolated_model_inference",
            expected_result_hash=str(manifest["result_data_hash"]),
        )

        def predictor(model: dict[str, Any]) -> PredictionBatch:
            for field in ("artifact_id", "artifact_hash", "feature_version", "schema_hash", "model_version"):
                if str(model.get(field) or "") != str(manifest.get(field) or ""):
                    raise ForecastTransactionError(
                        f"{field.upper()}_MISMATCH",
                        f"{field} 与 Active 模型身份不一致",
                    )
            return batch

        if context:
            context.log("persist", "原子写入 forecast_runs / forecast_results", progress=78)
        result = service.execute(request, predictor, run_id=run_id)
        return {
            "available": True,
            "execution_path": "t003_atomic_forecast",
            "run_id": result["run_id"],
            "status": result["status"],
            "rows": result["record_count"],
            "model_version": result["model_version"],
            "feature_version": result["feature_version"],
            "result_hash": result["result_hash"],
            "source_type": result["source_type"],
            "current_latest_write": False,
        }
    except Exception as exc:
        if context:
            context.log("predict", "Active 模型预测失败；已 fail-closed，未生成合成预测。", level="error", progress=62)
        raise RuntimeError("预测事务未完成，未写入任何预测事实。") from exc


def run_data_sync(payload: dict[str, Any], context: TaskStepLogger | None = None) -> dict[str, Any]:
    if context:
        context.log("parse", "读取数据同步参数", progress=18, metadata={"payload": payload})
        context.log("source_check", "检查核心事实表与电价规则数据源", progress=34)
    result = sync_core_facts_and_tariff_assets(log=lambda message: context.log("persist", message, progress=64) if context else None)
    if not result.get("available"):
        raise RuntimeError(str(result.get("message") or result))
    if context:
        context.log("validate", "校验同步结果", progress=88, metadata=result)
    return {"available": True, "execution_path": "core_data_sync", "result": result}


def run_report_daily(payload: dict[str, Any], context: TaskStepLogger | None = None) -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL 不可用，无法保存日报结果。")
    report_date = str(payload.get("report_date") or datetime.now().date().isoformat())
    region = str(payload.get("region") or "浙江省")
    report_type = str(payload.get("report_type") or "daily")
    if context:
        context.log("parse", "读取日报生成参数", progress=18, metadata={"report_date": report_date, "region": region, "report_type": report_type})
        context.log("load_data", "读取预测结果与任务运行摘要", progress=42)
    forecast = load_latest_forecast()
    overview = task_overview()
    summary = {
        "report_date": report_date,
        "region": region,
        "forecast_summary": forecast.get("summary") or {},
        "task_summary": {
            "task_total": overview.get("task_total", 0),
            "success_total": overview.get("success_total", 0),
            "failed_total": overview.get("failed_total", 0),
            "timeout_total": overview.get("timeout_total", 0),
        },
        "sections": [
            "电价预测摘要",
            "任务运行健康",
            "失败与超时任务复盘",
            "次日运行建议",
        ],
    }
    report_id = "daily_" + report_date.replace("-", "") + "_" + datetime.now().strftime("%H%M%S")
    title = f"{region}售电交易运行日报（{report_date}）"
    if context:
        context.log("generate", "生成结构化日报内容", progress=72, metadata={"report_id": report_id})
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO report_runs (
                    report_id, run_id, title, status, report_type, file_path,
                    metadata_json, content_json, generated_at
                )
                VALUES (
                    :report_id, :run_id, :title, 'ready', :report_type, :file_path,
                    CAST(:metadata_json AS jsonb), CAST(:content_json AS jsonb), :generated_at
                )
                ON CONFLICT (report_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    status = EXCLUDED.status,
                    report_type = EXCLUDED.report_type,
                    file_path = EXCLUDED.file_path,
                    metadata_json = EXCLUDED.metadata_json,
                    content_json = EXCLUDED.content_json,
                    generated_at = EXCLUDED.generated_at,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "report_id": report_id,
                "run_id": str(forecast.get("run_id") or "latest"),
                "title": title,
                "report_type": report_type,
                "file_path": "",
                "metadata_json": dumps_json({"region": region, "generated_by": "task_center_worker"}),
                "content_json": dumps_json(summary),
                "generated_at": datetime.now(),
            },
        )
    if context:
        context.log("persist", "保存日报结果到 report_runs", progress=90, metadata={"report_id": report_id})
    return {
        "available": True,
        "execution_path": "postgresql_report_runs",
        "report_id": report_id,
        "title": title,
        "report_date": report_date,
        "region": region,
        "summary": summary,
    }

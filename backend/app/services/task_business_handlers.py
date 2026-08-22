from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd
from backend.app.config import PROJECT_ROOT, runtime_asset_root
from backend.app.repositories.base import postgres_engine
from backend.app.services.core_data_sync import sync_core_facts_and_tariff_assets
from backend.app.services.forecast_transaction_service import (
    ForecastRunRequest,
    ForecastTransactionError,
    ForecastTransactionService,
    PredictionBatch,
    generate_run_id,
)
from backend.app.services.report_generation_service import generate_operational_report
from model_ops.result_hash import RESULT_VALUE_COLUMNS
from model_ops.safe_model_contract import (
    ModelContractError,
    build_artifact_manifest,
    build_feature_contract,
    prepare_frozen_24_input,
    sha256_file,
    validate_feature_batch,
)


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


def _isolated_inference_error_code(stderr: str) -> str:
    for code in re.findall(r"\b([A-Z][A-Z0-9_]{2,63})\s*:", str(stderr or "")):
        if code not in {"TRACEBACK", "ERROR"}:
            return code
    return "MODEL_INFERENCE_FAILED"


def _forecast_asset_root(service: ForecastTransactionService) -> Path:
    """Resolve shared read-only assets from config or the PostgreSQL model fact."""

    relative_input = Path("结果-3") / "结果表" / "18_未来24小时预测输入特征_正式版.xlsx"
    relative_runtime = Path(".codex_envs") / "t002_sklearn160" / "Scripts" / "python.exe"
    configured = runtime_asset_root()
    if (configured / relative_input).is_file() and (configured / relative_runtime).is_file():
        return configured

    active = service.active_model("price", "da_price")
    artifact_path = Path(str(active.get("artifact_path") or "")).resolve(strict=True)
    for candidate in artifact_path.parents:
        if (candidate / relative_input).is_file() and (candidate / relative_runtime).is_file():
            return candidate
    return configured


def run_price_predict(payload: dict[str, Any], context: TaskStepLogger | None = None) -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL 不可用，无法启动预测事务。")
    service = ForecastTransactionService(engine)
    run_id = generate_run_id()
    asset_root = _forecast_asset_root(service)
    input_path = asset_root / "结果-3" / "结果表" / "18_未来24小时预测输入特征_正式版.xlsx"
    if not input_path.exists():
        raise RuntimeError("严格 24×170 预测输入不存在；未创建 forecast run。")

    input_hash = sha256_file(input_path)
    try:
        raw_time = pd.read_excel(input_path, usecols=["datetime"], engine="openpyxl")
        input_timestamps = pd.DatetimeIndex(raw_time["datetime"])
        if input_timestamps.tz is not None:
            raise ForecastTransactionError("SOURCE_TIMEZONE_UNEXPECTED", "冻结输入时间不得重复携带时区")
        input_timestamps = input_timestamps.tz_localize(
            "America/New_York", ambiguous="raise", nonexistent="raise"
        )
        if len(input_timestamps) != 24 or input_timestamps.has_duplicates:
            raise ForecastTransactionError("INPUT_WINDOW_INVALID", "冻结输入必须包含 24 个唯一小时")
        diffs = input_timestamps.to_series(index=range(24)).diff().dropna()
        if not bool((diffs == pd.Timedelta(hours=1)).all()):
            raise ForecastTransactionError("NON_CONTIGUOUS_HOURS", "冻结输入必须连续 24 小时")
    except ForecastTransactionError:
        raise
    except Exception as exc:
        raise ForecastTransactionError("INPUT_HEADER_INVALID", "冻结输入时间字段无效") from exc

    request_key = str(payload.get("idempotency_key") or run_id).strip()
    generated_at = pd.Timestamp(input_path.stat().st_mtime, unit="s", tz="UTC").isoformat()
    source_metadata = {
        "data_source": "historical_frozen_business_features",
        "is_simulated": False,
        "generated_at": generated_at,
        "scenario": "v2_12_core_p0_historical_replay",
        "asset_name": input_path.name,
        "input_file_hash": input_hash,
        "timezone": "America/New_York",
        "row_count": 24,
        "feature_count": 170,
        "environment": "local_rc_historical_replay",
        "freshness_semantics": "historical_frozen_input_not_current_realtime",
    }
    request = ForecastRunRequest(
        domain="price",
        target_name="da_price",
        input_start_at=input_timestamps[0].to_pydatetime(),
        input_end_at=input_timestamps[-1].to_pydatetime(),
        input_hash=input_hash,
        environment_hash="pending_isolated_runtime",
        source_type="historical",
        source_metadata=source_metadata,
        freshness_status="stale",
        development_mode=False,
        idempotency_key=request_key,
    )

    try:
        active = service.active_model(request.domain, request.target_name)
        duplicate = service.find_idempotent_success(request, active)
        if duplicate:
            return {
                "available": True,
                "execution_path": "t003_atomic_forecast",
                "formal_worker": True,
                "idempotent": True,
                "run_id": duplicate["run_id"],
                "status": duplicate["status"],
                "rows": duplicate["record_count"],
                "input_batch_id": duplicate.get("input_batch_id"),
                "model_version": duplicate["model_version"],
                "feature_version": duplicate["feature_version"],
                "result_hash": duplicate["result_hash"],
                "source_type": duplicate["source_type"],
                "current_latest_write": False,
            }

        artifact_path = Path(str(active.get("artifact_path") or "")).resolve(strict=True)
        manifest = build_artifact_manifest(artifact_path)
        contract = build_feature_contract(artifact_path)
        contract["artifact_id"] = manifest["artifact_id"]
        for field in ("artifact_id", "artifact_hash", "model_version", "feature_version", "schema_hash"):
            if not active.get(field):
                raise ForecastTransactionError("MODEL_IDENTITY_INCOMPLETE", f"Active 模型缺少 {field}")
            if str(active[field]) != str(manifest[field]):
                raise ForecastTransactionError(field.upper() + "_MISMATCH", f"{field} 与 PostgreSQL 模型事实不一致")

        features, frozen_timestamps = prepare_frozen_24_input(
            input_path,
            input_path,
            contract,
            source_timezone="America/New_York",
        )
        validate_feature_batch(
            features,
            frozen_timestamps,
            contract,
            {
                "artifact_id": manifest["artifact_id"],
                "feature_version": manifest["feature_version"],
                "schema_hash": manifest["schema_hash"],
            },
        )

        isolated_python = asset_root / ".codex_envs" / "t002_sklearn160" / "Scripts" / "python.exe"
        if not isolated_python.exists():
            raise ForecastTransactionError("ISOLATED_RUNTIME_MISSING", "T002 隔离推理环境不存在")
        output_dir = PROJECT_ROOT / ".codex_tmp" / "t003_runtime" / run_id
        output_dir.mkdir(parents=True, exist_ok=False)
        temp_dir = PROJECT_ROOT / ".codex_tmp" / "task_runtime_tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        if context:
            context.log("parse", "创建统一预测 run_id", progress=18, metadata={"run_id": run_id})
            context.log("load_data", "读取 PostgreSQL Active 模型事实与冻结输入", progress=36)

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
                "T003_OPENPYXL_SITE_PACKAGES": str(asset_root / ".venv" / "Lib" / "site-packages"),
            }
        )
        child_env.pop("DATABASE_URL", None)
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
            code = _isolated_inference_error_code(completed.stderr)
            raise ForecastTransactionError(code, "隔离模型推理失败")

        prediction_manifest = json.loads(
            (output_dir / "prediction_manifest.json").read_text(encoding="utf-8")
        )
        timestamps = pd.DatetimeIndex(
            pd.to_datetime(
                json.loads((output_dir / "prediction_timestamps.json").read_text(encoding="utf-8")),
                utc=True,
            )
        ).tz_convert("America/New_York")
        if not timestamps.equals(frozen_timestamps):
            raise ForecastTransactionError("INPUT_TIMESTAMP_MISMATCH", "隔离推理时间与冻结输入不一致")
        values = pd.DataFrame(
            np.load(output_dir / "prediction_values.npy", allow_pickle=False),
            columns=list(RESULT_VALUE_COLUMNS),
        )
        batch = PredictionBatch(
            timestamps,
            values,
            input_features=features,
            input_hash=input_hash,
            environment_hash=str(prediction_manifest["environment_hash"]),
            manifest_result_hash=str(prediction_manifest["result_data_hash"]),
            source_versions={
                "input_contract": contract["contract_version"],
                "artifact_manifest": manifest["manifest_version"],
            },
            source_hashes={
                "input_file": input_hash,
                "artifact": manifest["artifact_hash"],
                "schema": manifest["schema_hash"],
            },
            source_metadata=source_metadata,
        )

        def predictor(model: dict[str, Any]) -> PredictionBatch:
            for field in ("artifact_id", "artifact_hash", "feature_version", "schema_hash", "model_version"):
                if str(model.get(field) or "") != str(prediction_manifest.get(field) or ""):
                    raise ForecastTransactionError(
                        f"{field.upper()}_MISMATCH",
                        f"{field} 与 Active 模型身份不一致",
                    )
            return batch

        if context:
            context.log("persist", "原子写入输入批次、forecast run 与 24 行结果", progress=78)
        result = service.execute(request, predictor, run_id=run_id)
        return {
            "available": True,
            "execution_path": "t003_atomic_forecast",
            "formal_worker": True,
            "idempotent": bool(result.get("idempotent")),
            "run_id": result["run_id"],
            "status": result["status"],
            "rows": result["record_count"],
            "input_batch_id": result.get("input_batch_id"),
            "model_version": result["model_version"],
            "feature_version": result["feature_version"],
            "result_hash": result["result_hash"],
            "source_type": result["source_type"],
            "current_latest_write": False,
        }
    except ModelContractError as exc:
        wrapped = ForecastTransactionError(exc.code, "冻结输入或模型静态契约校验失败")
        service.record_failure(request, run_id, wrapped)
        if context:
            context.log("validate", "模型或输入契约失败；结果为 0 行。", level="error", progress=62)
        raise wrapped from exc
    except ForecastTransactionError as exc:
        service.record_failure(request, run_id, exc)
        if context:
            context.log("predict", "正式预测失败；事务已回滚为 0 结果行。", level="error", progress=62)
        raise
    except Exception as exc:
        wrapped = ForecastTransactionError("FORECAST_RUNTIME_FAILED", "正式预测运行时失败")
        service.record_failure(request, run_id, wrapped)
        if context:
            context.log("predict", "正式预测失败；事务已回滚为 0 结果行。", level="error", progress=62)
        raise wrapped from exc

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
    requested_run_id = str(payload.get("run_id") or "latest")
    report_date = str(payload.get("report_date") or "") or None
    region = str(payload.get("region") or "模型覆盖市场")
    report_type = str(payload.get("report_type") or "daily")
    if context:
        context.log(
            "parse",
            "读取报告生成参数",
            progress=18,
            metadata={"run_id": requested_run_id, "report_date": report_date, "region": region, "report_type": report_type},
        )
        context.log("load_data", "读取唯一 success 预测批次与 24 行结果", progress=42)
    result = generate_operational_report(
        engine,
        run_id=requested_run_id,
        report_type=report_type,
        region=region,
        report_date=report_date,
    )
    if context:
        context.log("generate", "生成可追溯运营决策报告", progress=72, metadata={"report_id": result["report_id"], "run_id": result["run_id"]})
        context.log("persist", "原子保存报告记录与文件", progress=90, metadata={"report_id": result["report_id"], "idempotent": result["idempotent"]})
    result["execution_path"] = "phase5_c_operational_report"
    return result

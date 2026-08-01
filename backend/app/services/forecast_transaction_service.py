from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from model_ops.result_hash import RESULT_VALUE_COLUMNS, result_data_hash


RUN_STATES = frozenset({"created", "validating", "running", "success", "failed", "cancelled"})
RUN_TRANSITIONS = {
    "created": frozenset({"validating", "failed", "cancelled"}),
    "validating": frozenset({"running", "failed", "cancelled"}),
    "running": frozenset({"success", "failed", "cancelled"}),
    "success": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}
REQUIRED_IDENTITY_FIELDS = (
    "model_id",
    "model_version",
    "artifact_id",
    "artifact_hash",
    "feature_version",
    "schema_hash",
)


class ForecastTransactionError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ForecastRunRequest:
    domain: str
    target_name: str
    input_start_at: datetime
    input_end_at: datetime
    input_hash: str
    environment_hash: str
    source_type: str = "model_inference"
    retry_of_run_id: str | None = None
    expected_result_hash: str | None = None
    input_batch_id: str | None = None
    source_metadata: dict[str, Any] | None = None
    freshness_status: str | None = None
    development_mode: bool = False


@dataclass(frozen=True)
class PredictionBatch:
    timestamps: pd.DatetimeIndex
    values: pd.DataFrame


def generate_run_id(now: datetime | None = None) -> str:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return f"run_{current.strftime('%Y%m%dT%H%M%S%fZ')}_{uuid4().hex[:10]}"


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise ForecastTransactionError("TIMEZONE_MISSING", f"{field} 必须包含时区")
    return value.astimezone(timezone.utc)


def _safe_error_message(_: BaseException) -> str:
    return "预测事务失败，未提交任何预测结果。"


def _error_code(exc: BaseException) -> str:
    if isinstance(exc, IntegrityError):
        return "DATABASE_CONSTRAINT_CONFLICT"
    code = str(getattr(exc, "code", "") or "").strip().upper()
    if code and re.fullmatch(r"[A-Z0-9_]{3,64}", code):
        return code
    return "FORECAST_TRANSACTION_FAILED"


class ForecastTransactionService:
    def __init__(
        self,
        engine: Engine,
        *,
        model_resolver: Callable[[Connection, str, str], list[dict[str, Any]]] | None = None,
    ):
        if engine.dialect.name != "postgresql":
            raise ForecastTransactionError("POSTGRESQL_REQUIRED", "T003 事务服务仅支持 PostgreSQL")
        self.engine = engine
        self.model_resolver = model_resolver or self._active_models

    def active_model(self, domain: str, target_name: str) -> dict[str, Any]:
        with self.engine.connect() as conn:
            models = self.model_resolver(conn, domain, target_name)
        if not models:
            raise ForecastTransactionError("ACTIVE_MODEL_MISSING", "不存在唯一 Active 模型")
        if len(models) != 1:
            raise ForecastTransactionError("ACTIVE_MODEL_CONFLICT", "存在多个 Active 模型")
        return models[0]

    def execute(
        self,
        request: ForecastRunRequest,
        predictor: Callable[[dict[str, Any]], PredictionBatch],
        *,
        run_id: str | None = None,
        fault_injector: Callable[[str, int | None, Connection], None] | None = None,
        state_observer: Callable[[str], None] | None = None,
        exporter: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        safe_run_id = str(run_id or generate_run_id()).strip()
        if not re.fullmatch(r"run_\d{8}T\d{12}Z_[0-9a-f]{10}", safe_run_id):
            raise ForecastTransactionError("RUN_ID_INVALID", "run_id 格式无效")
        existing = self.get_run(safe_run_id)
        if existing:
            if existing["status"] == "success":
                return {**existing, "idempotent": True, "export_status": "not_repeated"}
            raise ForecastTransactionError(
                "RUN_ID_ALREADY_USED",
                f"run_id 已存在且状态为 {existing['status']}，禁止覆盖",
            )

        try:
            result = self._execute_transaction(
                safe_run_id,
                request,
                predictor,
                fault_injector=fault_injector,
                state_observer=state_observer,
            )
        except BaseException as exc:
            self._record_failed_run(safe_run_id, request, exc)
            if isinstance(exc, ForecastTransactionError):
                raise
            raise ForecastTransactionError(_error_code(exc), _safe_error_message(exc)) from exc

        export_status = "disabled"
        if exporter is not None:
            try:
                exporter(result)
                export_status = "success"
            except Exception:
                export_status = "failed_after_commit"
        return {**result, "idempotent": False, "export_status": export_status}

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM forecast_runs WHERE run_id = :run_id"),
                {"run_id": run_id},
            ).mappings().first()
        return dict(row) if row else {}

    def _execute_transaction(
        self,
        run_id: str,
        request: ForecastRunRequest,
        predictor: Callable[[dict[str, Any]], PredictionBatch],
        *,
        fault_injector: Callable[[str, int | None, Connection], None] | None,
        state_observer: Callable[[str], None] | None,
    ) -> dict[str, Any]:
        input_start = _utc(request.input_start_at, "input_start_at")
        input_end = _utc(request.input_end_at, "input_end_at")
        if input_end < input_start:
            raise ForecastTransactionError("INPUT_WINDOW_INVALID", "输入时间窗口无效")
        if not request.input_hash or not request.environment_hash:
            raise ForecastTransactionError("RUN_IDENTITY_INCOMPLETE", "input_hash 和 environment_hash 必须提供")

        with self.engine.begin() as conn:
            if request.retry_of_run_id:
                if request.retry_of_run_id == run_id:
                    raise ForecastTransactionError("RETRY_SELF_REFERENCE", "retry_of_run_id 不得引用自身")
                original = conn.execute(
                    text("SELECT run_id FROM forecast_runs WHERE run_id = :run_id"),
                    {"run_id": request.retry_of_run_id},
                ).first()
                if not original:
                    raise ForecastTransactionError("RETRY_RUN_MISSING", "retry_of_run_id 不存在")

            models = self.model_resolver(conn, request.domain, request.target_name)
            if not models:
                raise ForecastTransactionError("ACTIVE_MODEL_MISSING", "不存在唯一 Active 模型")
            if len(models) != 1:
                raise ForecastTransactionError("ACTIVE_MODEL_CONFLICT", "存在多个 Active 模型")
            model = models[0]
            missing = [field for field in REQUIRED_IDENTITY_FIELDS if not model.get(field)]
            if missing:
                raise ForecastTransactionError("MODEL_IDENTITY_INCOMPLETE", f"Active 模型身份缺失：{','.join(missing)}")

            now = datetime.now(timezone.utc)
            conn.execute(
                text(
                    """
                    INSERT INTO forecast_runs (
                        run_id, status, domain, target_name, input_start_at, input_end_at,
                        model_id, model_version, artifact_id, artifact_hash,
                        feature_version, schema_hash, input_hash, source_type,
                        created_at, started_at, retry_of_run_id, environment_hash,
                        record_count, row_count, input_batch_id, source_metadata_json,
                        freshness_status, development_mode
                    ) VALUES (
                        :run_id, 'created', :domain, :target_name, :input_start_at, :input_end_at,
                        :model_id, :model_version, :artifact_id, :artifact_hash,
                        :feature_version, :schema_hash, :input_hash, :source_type,
                        :created_at, :started_at, :retry_of_run_id, :environment_hash,
                        0, 0, :input_batch_id, CAST(:source_metadata_json AS jsonb),
                        :freshness_status, :development_mode
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "domain": request.domain,
                    "target_name": request.target_name,
                    "input_start_at": input_start,
                    "input_end_at": input_end,
                    "input_hash": request.input_hash,
                    "source_type": request.source_type,
                    "created_at": now,
                    "started_at": now,
                    "retry_of_run_id": request.retry_of_run_id,
                    "environment_hash": request.environment_hash,
                    "input_batch_id": request.input_batch_id,
                    "source_metadata_json": json.dumps(request.source_metadata or {}, ensure_ascii=False, default=str),
                    "freshness_status": request.freshness_status,
                    "development_mode": bool(request.development_mode),
                    **{field: model[field] for field in REQUIRED_IDENTITY_FIELDS},
                },
            )
            self._observe("created", state_observer)
            self._transition(conn, run_id, "created", "validating")
            self._observe("validating", state_observer)
            if fault_injector:
                fault_injector("before_predict", None, conn)
            batch = predictor(model)
            timestamps, values = self._validate_batch(batch, model)
            data_hash = result_data_hash(timestamps, values)
            if request.expected_result_hash and data_hash != request.expected_result_hash:
                raise ForecastTransactionError(
                    "RESULT_HASH_MISMATCH",
                    "预测结果与隔离推理 manifest 的 result_hash 不一致",
                )
            self._transition(conn, run_id, "validating", "running")
            self._observe("running", state_observer)

            generated_at = datetime.now(timezone.utc)
            for index, timestamp in enumerate(timestamps):
                if fault_injector:
                    fault_injector("before_insert", index + 1, conn)
                row = values.iloc[index]
                component_outputs = {
                    name: float(row[name])
                    for name in RESULT_VALUE_COLUMNS
                    if name in row
                }
                conn.execute(
                    text(
                        """
                        INSERT INTO forecast_results (
                            run_id, forecast_time, forecast_datetime, predicted_price,
                            model_version, feature_version, generated_at,
                            base_prediction, peak_prediction, classifier_prediction,
                            spike_risk_prob, p90_prediction, blend_weight,
                            component_outputs, source_type, source_row, raw_json,
                            input_batch_id, forecast_load, risk_level
                        ) VALUES (
                            :run_id, :forecast_time, :forecast_datetime, :predicted_price,
                            :model_version, :feature_version, :generated_at,
                            :base_prediction, :peak_prediction, :classifier_prediction,
                            :spike_probability, :p90_prediction, :blend_weight,
                            CAST(:component_outputs AS jsonb), :source_type, :source_row,
                            CAST(:component_outputs AS jsonb), :input_batch_id,
                            :forecast_load, :risk_level
                        )
                        """
                    ),
                    {
                        "run_id": run_id,
                        "forecast_time": timestamp.to_pydatetime(),
                        "forecast_datetime": timestamp.tz_convert("UTC").tz_localize(None).to_pydatetime(),
                        "predicted_price": float(row["predicted_price"]),
                        "model_version": model["model_version"],
                        "feature_version": model["feature_version"],
                        "generated_at": generated_at,
                        "base_prediction": float(row["base_prediction"]),
                        "peak_prediction": float(row["peak_prediction"]),
                        "classifier_prediction": float(row["classifier_prediction"]),
                        "spike_probability": float(row["spike_probability"]),
                        "p90_prediction": float(row["p90_prediction"]),
                        "blend_weight": float(row["blend_weight"]),
                        "component_outputs": pd.Series(component_outputs).to_json(),
                        "source_type": request.source_type,
                        "source_row": index + 1,
                        "input_batch_id": request.input_batch_id,
                        "forecast_load": float(row["forecast_load"]) if "forecast_load" in row and pd.notna(row["forecast_load"]) else None,
                        "risk_level": str(row["risk_level"]) if "risk_level" in row else None,
                    },
                )

            count = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM forecast_results WHERE run_id = :run_id"),
                    {"run_id": run_id},
                ).scalar_one()
            )
            if count != 24:
                raise ForecastTransactionError("RESULT_COUNT_INVALID", f"结果数量必须为 24，实际 {count}")
            if fault_injector:
                fault_injector("before_success", None, conn)
            finished_at = datetime.now(timezone.utc)
            updated = conn.execute(
                text(
                    """
                    UPDATE forecast_runs
                    SET status = 'success', forecast_start_at = :forecast_start_at,
                        forecast_end_at = :forecast_end_at, forecast_start = :forecast_start,
                        forecast_end = :forecast_end, generated_at = :generated_at,
                        result_hash = :result_hash, record_count = 24, row_count = 24,
                        finished_at = :finished_at, updated_at = CURRENT_TIMESTAMP,
                        error_code = NULL, error_message = NULL
                    WHERE run_id = :run_id AND status = 'running'
                    """
                ),
                {
                    "run_id": run_id,
                    "forecast_start_at": timestamps[0].to_pydatetime(),
                    "forecast_end_at": timestamps[-1].to_pydatetime(),
                    "forecast_start": timestamps[0].tz_convert("UTC").tz_localize(None).to_pydatetime(),
                    "forecast_end": timestamps[-1].tz_convert("UTC").tz_localize(None).to_pydatetime(),
                    "generated_at": generated_at,
                    "result_hash": data_hash,
                    "finished_at": finished_at,
                },
            )
            if updated.rowcount != 1:
                raise ForecastTransactionError("SUCCESS_STATE_UPDATE_FAILED", "success 状态更新失败")
            self._observe("success", state_observer)

        return self.get_run(run_id)

    @staticmethod
    def _observe(status: str, observer: Callable[[str], None] | None) -> None:
        if observer:
            observer(status)

    @staticmethod
    def _transition(conn: Connection, run_id: str, current: str, target: str) -> None:
        if target not in RUN_TRANSITIONS.get(current, frozenset()):
            raise ForecastTransactionError("STATE_TRANSITION_INVALID", f"{current} 不允许转换为 {target}")
        result = conn.execute(
            text(
                """
                UPDATE forecast_runs SET status = :target, updated_at = CURRENT_TIMESTAMP
                WHERE run_id = :run_id AND status = :current
                """
            ),
            {"run_id": run_id, "current": current, "target": target},
        )
        if result.rowcount != 1:
            raise ForecastTransactionError("STATE_TRANSITION_CONFLICT", f"{current}→{target} 更新失败")

    @staticmethod
    def _validate_batch(
        batch: PredictionBatch,
        model: dict[str, Any],
    ) -> tuple[pd.DatetimeIndex, pd.DataFrame]:
        if not isinstance(batch, PredictionBatch):
            raise ForecastTransactionError("PREDICTION_BATCH_INVALID", "predictor 必须返回 PredictionBatch")
        timestamps = pd.DatetimeIndex(batch.timestamps)
        values = batch.values.copy()
        if len(timestamps) != 24 or len(values) != 24:
            raise ForecastTransactionError("RESULT_COUNT_INVALID", "预测必须恰好返回 24 行")
        if timestamps.tz is None:
            raise ForecastTransactionError("TIMEZONE_MISSING", "预测时间必须包含时区")
        if timestamps.has_duplicates:
            raise ForecastTransactionError("DUPLICATE_FORECAST_TIME", "预测时间存在重复")
        diffs = timestamps.to_series(index=range(24)).diff().dropna()
        if not bool((diffs == pd.Timedelta(hours=1)).all()):
            raise ForecastTransactionError("FORECAST_TIME_NOT_CONTIGUOUS", "预测时间必须连续 24 小时")
        missing = [name for name in RESULT_VALUE_COLUMNS if name not in values.columns]
        if missing:
            raise ForecastTransactionError("RESULT_COLUMNS_MISSING", f"预测结果缺少列：{','.join(missing)}")
        matrix = values[list(RESULT_VALUE_COLUMNS)].to_numpy(dtype="float64")
        if not np.isfinite(matrix).all():
            raise ForecastTransactionError("RESULT_NONFINITE", "预测结果包含 NaN 或 Inf")
        if values[list(RESULT_VALUE_COLUMNS)].shape != (24, len(RESULT_VALUE_COLUMNS)):
            raise ForecastTransactionError("RESULT_SHAPE_INVALID", "预测结果 shape 无效")
        if any(not math.isfinite(float(item)) for item in values["predicted_price"]):
            raise ForecastTransactionError("RESULT_NONFINITE", "predicted_price 包含非有限值")
        if not model.get("model_version") or not model.get("feature_version"):
            raise ForecastTransactionError("MODEL_IDENTITY_INCOMPLETE", "结果缺少模型或特征身份")
        return timestamps, values

    def _record_failed_run(
        self,
        run_id: str,
        request: ForecastRunRequest,
        exc: BaseException,
    ) -> None:
        code = _error_code(exc)
        message = _safe_error_message(exc)
        try:
            with self.engine.begin() as conn:
                existing = conn.execute(
                    text("SELECT status FROM forecast_runs WHERE run_id = :run_id FOR UPDATE"),
                    {"run_id": run_id},
                ).mappings().first()
                if existing:
                    return
                conn.execute(
                    text(
                        """
                        INSERT INTO forecast_runs (
                            run_id, status, domain, target_name,
                            input_start_at, input_end_at, input_hash, environment_hash,
                            source_type, retry_of_run_id, record_count, row_count,
                            error_code, error_message, created_at, started_at, finished_at
                        ) VALUES (
                            :run_id, 'failed', :domain, :target_name,
                            :input_start_at, :input_end_at, :input_hash, :environment_hash,
                            :source_type, :retry_of_run_id, 0, 0,
                            :error_code, :error_message, :created_at, :created_at, :created_at
                        )
                        """
                    ),
                    {
                        "run_id": run_id,
                        "domain": request.domain,
                        "target_name": request.target_name,
                        "input_start_at": _utc(request.input_start_at, "input_start_at"),
                        "input_end_at": _utc(request.input_end_at, "input_end_at"),
                        "input_hash": request.input_hash,
                        "environment_hash": request.environment_hash,
                        "source_type": request.source_type,
                        "retry_of_run_id": request.retry_of_run_id,
                        "error_code": code,
                        "error_message": message,
                        "created_at": datetime.now(timezone.utc),
                    },
                )
        except Exception:
            # The original failure remains authoritative. Never mutate a prior
            # successful run merely to persist secondary failure telemetry.
            return

    @staticmethod
    def _active_models(conn: Connection, domain: str, target_name: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            text(
                """
                SELECT model_id, model_version, artifact_id, artifact_path,
                       artifact_hash, feature_version, schema_hash, source_type
                FROM model_registry
                WHERE domain = :domain AND target_name = :target_name
                  AND LOWER(status) = 'active' AND is_active = 1
                ORDER BY activated_at DESC, created_at DESC
                FOR SHARE
                """
            ),
            {"domain": domain, "target_name": target_name},
        ).mappings().all()
        return [dict(row) for row in rows]

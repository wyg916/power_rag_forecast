from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, text

from backend.app.core.config import get_settings
from backend.app.core.security import CurrentUser
from backend.app.services.model_fact_service import (
    DEFAULT_MODEL_DOMAIN,
    DEFAULT_TARGET_NAME,
    ModelFactError,
    ModelFactService,
)

from .base import dumps_json, jsonable, loads_json, mapping_dict, mapping_list, postgres_engine


MODEL_SEED_VERSIONS: list[dict[str, Any]] = [
    {
        "model_version": "v3.3.0-rc1",
        "model_name": "load-forecast-candidate",
        "model_type": "负荷预测模型",
        "status": "Candidate",
        "is_active": False,
        "artifact_path": "model_artifacts/load_forecast/v3.3.0-rc1",
        "created_at": "2025-06-21 09:45:12",
        "metrics": {"mae": 15.42, "rmse": 23.67, "mape": 7.21, "peak_error": 68.43, "sample_count": 1892743},
    },
    {
        "model_version": "v3.2.1",
        "model_name": "load-forecast-active",
        "model_type": "负荷预测模型",
        "status": "Active",
        "is_active": True,
        "artifact_path": "model_artifacts/load_forecast/v3.2.1",
        "created_at": "2025-06-19 22:18:33",
        "metrics": {"mae": 16.81, "rmse": 25.54, "mape": 7.89, "peak_error": 75.61, "sample_count": 1840200},
    },
    {
        "model_version": "v3.2.0",
        "model_name": "load-forecast-archived",
        "model_type": "负荷预测模型",
        "status": "Archived",
        "is_active": False,
        "artifact_path": "model_artifacts/load_forecast/v3.2.0",
        "created_at": "2025-06-18 21:05:11",
        "metrics": {"mae": 17.98, "rmse": 27.32, "mape": 8.31, "peak_error": 80.92, "sample_count": 1796000},
    },
    {
        "model_version": "v3.1.2",
        "model_name": "load-forecast-archived",
        "model_type": "负荷预测模型",
        "status": "Archived",
        "is_active": False,
        "artifact_path": "model_artifacts/load_forecast/v3.1.2",
        "created_at": "2025-06-17 20:10:08",
        "metrics": {"mae": 19.45, "rmse": 29.81, "mape": 8.92, "peak_error": 86.47, "sample_count": 1715000},
    },
    {
        "model_version": "v3.1.1",
        "model_name": "load-forecast-archived",
        "model_type": "负荷预测模型",
        "status": "Archived",
        "is_active": False,
        "artifact_path": "model_artifacts/load_forecast/v3.1.1",
        "created_at": "2025-06-16 19:42:56",
        "metrics": {"mae": 20.31, "rmse": 31.20, "mape": 9.36, "peak_error": 90.13, "sample_count": 1689000},
    },
]


def _ensure_prediction_comparison_table(conn: Any) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS model_prediction_comparison_points (
                id BIGSERIAL PRIMARY KEY,
                model_type VARCHAR(64) NOT NULL DEFAULT '负荷预测模型',
                region VARCHAR(64) NOT NULL DEFAULT '浙江省',
                forecast_time TIMESTAMP NOT NULL,
                active_version VARCHAR(128) NOT NULL,
                candidate_version VARCHAR(128) NOT NULL,
                actual_value DOUBLE PRECISION,
                active_prediction DOUBLE PRECISION,
                candidate_prediction DOUBLE PRECISION,
                diff_value DOUBLE PRECISION,
                granularity VARCHAR(32) NOT NULL DEFAULT '15分钟',
                data_origin VARCHAR(32) NOT NULL DEFAULT 'seed',
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uk_model_prediction_comparison_points UNIQUE (
                    model_type, region, forecast_time, active_version, candidate_version
                )
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_model_prediction_comparison_time
            ON model_prediction_comparison_points(forecast_time)
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_model_prediction_comparison_versions
            ON model_prediction_comparison_points(active_version, candidate_version)
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_model_prediction_comparison_region
            ON model_prediction_comparison_points(model_type, region)
            """
        )
    )


def _metric_on_day(base: dict[str, Any], days_back: int, phase: float = 0.0) -> dict[str, float]:
    drift = days_back * 0.12
    wobble = ((days_back % 5) - 2) * 0.18 + phase
    return {
        "mae": round(float(base["mae"]) + drift + wobble, 2),
        "rmse": round(float(base["rmse"]) + drift * 1.35 + wobble * 1.2, 2),
        "mape": round(float(base["mape"]) + drift * 0.08 + wobble * 0.05, 2),
        "peak_error": round(float(base["peak_error"]) + drift * 1.8 + wobble * 2.0, 2),
    }


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _chart_time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%m-%d %H:%M")
    text_value = str(value or "")
    if len(text_value) >= 16:
        return text_value[5:16]
    return text_value


def _seed_prediction_comparison_points(
    active: dict[str, Any],
    candidate: dict[str, Any],
    *,
    model_type: str,
    region: str,
    days: int = 7,
) -> bool:
    engine = postgres_engine()
    active_version = str(active.get("model_version") or "")
    candidate_version = str(candidate.get("model_version") or "")
    if engine is None or not active_version or not candidate_version:
        return False
    safe_days = max(1, min(int(days or 7), 30))
    expected_rows = safe_days * 96
    try:
        with engine.begin() as conn:
            _ensure_prediction_comparison_table(conn)
            existing = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM model_prediction_comparison_points
                        WHERE model_type = :model_type
                          AND region = :region
                          AND active_version = :active_version
                          AND candidate_version = :candidate_version
                        """
                    ),
                    {
                        "model_type": model_type,
                        "region": region,
                        "active_version": active_version,
                        "candidate_version": candidate_version,
                    },
                ).scalar()
                or 0
            )
            if existing >= expected_rows:
                return True

            start_at = datetime(2025, 6, 15, 0, 0)
            active_mae = _as_float(active.get("mae") or active.get("test_mae"), 16.8)
            candidate_mae = _as_float(candidate.get("mae") or candidate.get("test_mae"), 15.4)
            for index in range(expected_rows):
                forecast_time = start_at + timedelta(minutes=15 * index)
                hour = forecast_time.hour + forecast_time.minute / 60
                day_offset = (forecast_time.date() - start_at.date()).days
                day_wave = math.sin((hour - 6) / 24 * math.pi * 2)
                evening_wave = max(0.0, math.sin((hour - 15) / 10 * math.pi))
                actual = 168 + max(0.0, day_wave) * 78 + evening_wave * 34 + (day_offset % 3) * 5
                active_error = active_mae * (0.055 + (index % 9) * 0.003)
                candidate_error = candidate_mae * (0.048 + (index % 7) * 0.0025)
                if hour < 5:
                    active_error *= -0.65
                    candidate_error *= -0.55
                row = {
                    "model_type": model_type,
                    "region": region,
                    "forecast_time": forecast_time,
                    "active_version": active_version,
                    "candidate_version": candidate_version,
                    "actual_value": round(actual, 3),
                    "active_prediction": round(actual + active_error, 3),
                    "candidate_prediction": round(actual + candidate_error, 3),
                    "diff_value": round(candidate_error - active_error, 3),
                    "metadata_json": dumps_json(
                        {
                            "source": "model_center_seed",
                            "active_mae": active_mae,
                            "candidate_mae": candidate_mae,
                        }
                    ),
                }
                conn.execute(
                    text(
                        """
                        INSERT INTO model_prediction_comparison_points (
                            model_type, region, forecast_time, active_version, candidate_version,
                            actual_value, active_prediction, candidate_prediction, diff_value,
                            granularity, data_origin, metadata_json, created_at, updated_at
                        )
                        VALUES (
                            :model_type, :region, :forecast_time, :active_version, :candidate_version,
                            :actual_value, :active_prediction, :candidate_prediction, :diff_value,
                            '15分钟', 'seed', CAST(:metadata_json AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (
                            model_type, region, forecast_time, active_version, candidate_version
                        )
                        DO UPDATE SET
                            actual_value = EXCLUDED.actual_value,
                            active_prediction = EXCLUDED.active_prediction,
                            candidate_prediction = EXCLUDED.candidate_prediction,
                            diff_value = EXCLUDED.diff_value,
                            metadata_json = EXCLUDED.metadata_json,
                            updated_at = CURRENT_TIMESTAMP
                        """
                    ),
                    row,
                )
        return True
    except Exception:
        return False


def _prediction_points_from_postgres(
    active: dict[str, Any],
    candidate: dict[str, Any],
    *,
    model_type: str,
    region: str,
    days: int = 7,
) -> list[dict[str, Any]]:
    engine = postgres_engine()
    active_version = str(active.get("model_version") or "")
    candidate_version = str(candidate.get("model_version") or "")
    if engine is None or not active_version or not candidate_version:
        return []
    safe_days = max(1, min(int(days or 7), 30))
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT forecast_time, actual_value, active_prediction,
                           candidate_prediction, diff_value, data_origin
                    FROM model_prediction_comparison_points
                    WHERE model_type = :model_type
                      AND region = :region
                      AND active_version = :active_version
                      AND candidate_version = :candidate_version
                    ORDER BY forecast_time
                    LIMIT :limit
                    """
                ),
                {
                    "model_type": model_type,
                    "region": region,
                    "active_version": active_version,
                    "candidate_version": candidate_version,
                    "limit": safe_days * 96,
                },
            ).mappings().all()
    except Exception:
        return []
    points = []
    for row in mapping_list(rows):
        points.append(
            {
                "time": _chart_time(row.get("forecast_time")),
                "actual": row.get("actual_value"),
                "active": row.get("active_prediction"),
                "candidate": row.get("candidate_prediction"),
                "diff": row.get("diff_value"),
                "data_origin": row.get("data_origin"),
            }
        )
    return jsonable(points)


def ensure_seed_model_center(*, explicit: bool = False) -> bool:
    """Legacy demo seed; never allowed from a read or production path."""

    if not explicit or not get_settings().is_test:
        return False
    engine = postgres_engine()
    if engine is None:
        return False
    with engine.begin() as conn:
        _ensure_prediction_comparison_table(conn)
        has_active = bool(conn.execute(text("SELECT 1 FROM model_versions WHERE is_active IS TRUE LIMIT 1")).scalar())
        for item in MODEL_SEED_VERSIONS:
            seed_active = bool(item["is_active"]) and not has_active
            seed_status = "Active" if seed_active else ("Candidate" if item["status"] == "Candidate" else "Archived")
            conn.execute(
                text(
                    """
                        INSERT INTO model_versions (
                            model_version, model_name, model_type, artifact_path, status,
                            is_active, metrics_json, created_at, updated_at
                        )
                        VALUES (
                            :model_version, :model_name, :model_type, :artifact_path, :status,
                            :is_active, CAST(:metrics_json AS jsonb), :created_at, :created_at
                        )
                        ON CONFLICT (model_version) DO UPDATE SET
                            model_name = EXCLUDED.model_name,
                            model_type = EXCLUDED.model_type,
                            artifact_path = EXCLUDED.artifact_path,
                            status = EXCLUDED.status,
                            is_active = EXCLUDED.is_active,
                            metrics_json = COALESCE(model_versions.metrics_json, EXCLUDED.metrics_json),
                            updated_at = CURRENT_TIMESTAMP
                        """
                ),
                {
                    "model_version": item["model_version"],
                    "model_name": item["model_name"],
                    "model_type": item["model_type"],
                    "artifact_path": item["artifact_path"],
                    "status": seed_status,
                    "is_active": seed_active,
                    "created_at": item["created_at"],
                    "metrics_json": dumps_json(
                        {
                            **item["metrics"],
                            "region": "浙江省",
                            "granularity": "15分钟",
                            "horizon": "24小时",
                            "algorithm": "LightGBM + 时序特征融合",
                            "data_origin": "seed",
                        }
                    ),
                },
            )
        today = date(2025, 6, 21)
        for version_index, item in enumerate(MODEL_SEED_VERSIONS[:2]):
            for days_back in range(30):
                metric_date = today - timedelta(days=days_back)
                metric = _metric_on_day(item["metrics"], days_back, phase=version_index * 0.2)
                conn.execute(
                    text(
                        """
                        INSERT INTO model_metrics (
                            model_version, metric_date, mae, rmse, r2, mape, peak_error,
                            sample_count, metrics_json, created_at
                        )
                        SELECT CAST(:model_version AS varchar), CAST(:metric_date AS date),
                               CAST(:mae AS double precision), CAST(:rmse AS double precision),
                               CAST(:r2 AS double precision), CAST(:mape AS double precision),
                               CAST(:peak_error AS double precision), CAST(:sample_count AS integer),
                               CAST(:metrics_json AS jsonb), CURRENT_TIMESTAMP
                        WHERE NOT EXISTS (
                            SELECT 1 FROM model_metrics
                            WHERE model_version = :model_version AND metric_date = :metric_date
                        )
                        """
                    ),
                    {
                        "model_version": item["model_version"],
                        "metric_date": metric_date,
                        "mae": metric["mae"],
                        "rmse": metric["rmse"],
                        "r2": 0.89,
                        "mape": metric["mape"],
                        "peak_error": metric["peak_error"],
                        "sample_count": item["metrics"]["sample_count"],
                        "metrics_json": dumps_json({"data_origin": "seed", "source": "model_center_seed"}),
                    },
                )
        conn.execute(
            text(
                """
                INSERT INTO task_runs (
                    task_id, run_id, task_name, task_kind, status, payload_json,
                    started_at, ended_at, duration_seconds, created_at, updated_at
                )
                SELECT 'train_20250621_094512', 'train_20250621_094512',
                       '模型中心候选模型训练', 'retrain_model', 'success',
                       CAST(:payload AS jsonb), '2025-06-21 09:12:54',
                       '2025-06-21 09:45:12', 1938, '2025-06-21 09:12:54',
                       '2025-06-21 09:45:12'
                WHERE NOT EXISTS (
                    SELECT 1 FROM task_runs WHERE task_id = 'train_20250621_094512'
                )
                """
            ),
            {"payload": dumps_json({"candidate_model_version": "v3.3.0-rc1", "sample_count": 1892743, "data_origin": "seed"})},
        )
        for event in [
            {
                "event_id": "mge_seed_train_20250621",
                "action": "training.completed",
                "target_version": "v3.3.0-rc1",
                "source_version": "",
                "operator": "system",
                "reason": "候选模型训练完成并生成评估指标",
                "status": "success",
                "metadata_json": dumps_json({"task_id": "train_20250621_094512", "data_origin": "seed"}),
                "created_at": "2025-06-21 09:45:12",
            },
            {
                "event_id": "mge_seed_admission_20250621",
                "action": "admission.passed",
                "target_version": "v3.3.0-rc1",
                "source_version": "v3.2.1",
                "operator": "system",
                "reason": "候选模型核心误差指标优于当前 Active 模型",
                "status": "success",
                "metadata_json": dumps_json({"rules": ["mae", "rmse", "peak_error"], "data_origin": "seed"}),
                "created_at": "2025-06-21 09:46:00",
            },
        ]:
            conn.execute(
                text(
                    """
                    INSERT INTO model_governance_events (
                        event_id, action, target_version, source_version, operator,
                        reason, status, metadata_json, created_at
                    )
                    VALUES (
                        :event_id, :action, :target_version, :source_version, :operator,
                        :reason, :status, CAST(:metadata_json AS jsonb), :created_at
                    )
                    ON CONFLICT (event_id) DO NOTHING
                    """
                ),
                event,
            )
    try:
        with engine.connect() as conn:
            log_count = int(
                conn.execute(text("SELECT COUNT(*) FROM task_logs WHERE task_id = 'train_20250621_094512'")).scalar()
                or 0
            )
        if log_count == 0:
            from .task_repository import append_task_log

            append_task_log(
                "train_20250621_094512",
                level="info",
                step="prepare",
                message="已加载训练样本并完成特征窗口检查。",
                status="success",
                task_name="模型中心候选模型训练",
                task_kind="retrain_model",
                sequence_no=1,
            )
            append_task_log(
                "train_20250621_094512",
                level="info",
                step="train",
                message="候选模型 v3.3.0-rc1 训练完成，生成评估指标和模型产物路径。",
                status="success",
                task_name="模型中心候选模型训练",
                task_kind="retrain_model",
                sequence_no=2,
            )
            append_task_log(
                "train_20250621_094512",
                level="info",
                step="evaluate",
                message="准入规则校验通过，候选模型进入待切换状态。",
                status="success",
                task_name="模型中心候选模型训练",
                task_kind="retrain_model",
                sequence_no=3,
            )
    except Exception:
        pass
    return True


def _merge_metrics(version: dict[str, Any], latest_metric: dict[str, Any] | None) -> dict[str, Any]:
    row = dict(version)
    metric = latest_metric or {}
    row.update(
        {
            "mae": metric.get("mae") if metric.get("mae") is not None else row.get("test_mae"),
            "rmse": metric.get("rmse") if metric.get("rmse") is not None else row.get("test_rmse"),
            "mape": metric.get("mape"),
            "peak_error": metric.get("peak_error") if metric.get("peak_error") is not None else row.get("peak_rmse"),
            "sample_count": metric.get("sample_count"),
            "metric_date": metric.get("metric_date"),
        }
    )
    row["is_active"] = bool(row.get("is_active"))
    state = str(row.get("status") or "").lower()
    row["activation_eligible"] = state == "validated" and not row["is_active"]
    row["rollback_eligible"] = state == "archived" and bool(row.get("validated_at"))
    return jsonable(row)


def model_status_from_postgres(
    *, domain: str = DEFAULT_MODEL_DOMAIN, target_name: str = DEFAULT_TARGET_NAME
) -> dict[str, Any] | None:
    engine = postgres_engine()
    if engine is None:
        return None
    try:
        service = ModelFactService(engine)
        raw_versions = service.list_models(domain, target_name)
        raw_active = service.get_active_model(domain, target_name)
        latest_metrics = _latest_metrics_by_version()
        versions = [
            _merge_metrics(item, latest_metrics.get(str(item.get("model_version") or "")))
            for item in raw_versions
        ]
        active = _merge_metrics(
            raw_active,
            latest_metrics.get(str(raw_active.get("model_version") or "")),
        ) if raw_active else {}
        with engine.connect() as conn:
            error_rows = conn.execute(
                text(
                    """
                    SELECT model_version, COUNT(*) AS sample_count,
                           AVG(abs_error) AS mae, MAX(abs_error) AS max_abs_error,
                           MAX(created_at) AS latest_record
                    FROM prediction_tracking
                    WHERE actual_price IS NOT NULL
                    GROUP BY model_version
                    ORDER BY latest_record DESC
                    LIMIT 60
                    """
                )
            ).mappings().all()
    except Exception:
        return None
    return {
        "active": jsonable(active),
        "versions": jsonable(versions),
        "errors": mapping_list(error_rows),
        "available": bool(versions),
        "empty_state": None if active else "当前 domain/target 没有 Active 模型",
        "domain": domain,
        "target_name": target_name,
        "source": "model_registry",
        "source_type": "registry",
    }


def model_errors_from_postgres() -> dict[str, Any] | None:
    payload = model_status_from_postgres()
    if payload is None:
        return None
    return {"records": payload.get("errors") or []}


def _latest_metrics_by_version() -> dict[str, dict[str, Any]]:
    engine = postgres_engine()
    if engine is None:
        return {}
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT model_version, metric_date, mae, rmse, mape,
                       peak_error, sample_count, created_at
                FROM (
                    SELECT model_version, metric_date, mae, rmse, mape,
                           peak_error, sample_count, created_at,
                           ROW_NUMBER() OVER (
                               PARTITION BY model_version
                               ORDER BY metric_date DESC, created_at DESC
                           ) AS row_no
                    FROM model_metrics
                ) ranked_metrics
                WHERE row_no = 1
                """
            )
        ).mappings().all()
    return {row["model_version"]: jsonable(dict(row)) for row in rows}


def _metric_history(model_versions: list[str], days: int = 30) -> list[dict[str, Any]]:
    engine = postgres_engine()
    if engine is None or not model_versions:
        return []
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT model_version, metric_date, mae, rmse, mape, peak_error, sample_count
                FROM model_metrics
                WHERE model_version IN :versions
                ORDER BY metric_date DESC, created_at DESC
                LIMIT :limit
                """
            ).bindparams(bindparam("versions", expanding=True)),
            {"versions": model_versions, "limit": max(days * len(model_versions), 1)},
        ).mappings().all()
    return mapping_list(rows)


def _training_status() -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {}
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT task_id, task_name, task_kind, status, payload_json, started_at,
                           ended_at, duration_seconds, created_at, updated_at
                    FROM task_runs
                    WHERE task_kind IN ('retrain_model', 'model_auto_optimize')
                    ORDER BY COALESCE(ended_at, started_at, created_at) DESC NULLS LAST
                    LIMIT 1
                    """
                )
            ).mappings().first()
    except Exception:
        return {}
    data = jsonable(dict(row)) if row else {}
    payload = loads_json(data.get("payload_json"), default={})
    data["payload"] = payload
    data["sample_count"] = payload.get("sample_count") or payload.get("training_sample_count")
    return data


def _governance_events(limit: int = 20) -> list[dict[str, Any]]:
    engine = postgres_engine()
    if engine is None:
        return []
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT event_id, action, target_version, source_version, operator,
                           reason, status, metadata_json, created_at
                    FROM model_governance_events
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                    """
                ),
                {"limit": max(1, min(int(limit or 20), 100))},
            ).mappings().all()
    except Exception:
        return []
    items = mapping_list(rows)
    for item in items:
        item["metadata"] = loads_json(item.pop("metadata_json", None), default={})
    return items


def _improvement(active: dict[str, Any], candidate: dict[str, Any], key: str) -> float:
    active_value = float(active.get(key) or 0)
    candidate_value = float(candidate.get(key) or 0)
    if active_value <= 0:
        return 0.0
    return round((active_value - candidate_value) / active_value * 100, 2)


def _has_quality_metrics(item: dict[str, Any]) -> bool:
    return any(item.get(key) is not None for key in ["mae", "rmse", "mape", "peak_error", "test_mae", "test_rmse", "peak_rmse"])


def _effect_points(active: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    base = 190.0
    for day in range(7):
        for hour in [0, 4, 8, 12, 16, 20]:
            wave = 55 if hour in [8, 12, 16] else 18
            actual = base + wave + (day % 3) * 8 - (12 if hour == 0 else 0)
            active_error = float(active.get("mae") or 16.8) * (0.6 + (hour % 5) * 0.04)
            candidate_error = float(candidate.get("mae") or 15.4) * (0.55 + (hour % 5) * 0.035)
            points.append(
                {
                    "time": f"06-{15 + day:02d} {hour:02d}:00",
                    "actual": round(actual, 2),
                    "active": round(actual + active_error, 2),
                    "candidate": round(actual + candidate_error, 2),
                    "diff": round(candidate_error - active_error, 2),
                }
            )
    return points


def model_center_overview(
    *,
    model_type: str = "",
    region: str = "",
    days: int = 7,
    search: str = "",
    domain: str = DEFAULT_MODEL_DOMAIN,
    target_name: str = DEFAULT_TARGET_NAME,
) -> dict[str, Any]:
    effective_model_type = model_type or "电价预测模型"
    effective_region = region or "浙江省"
    payload = model_status_from_postgres(domain=domain, target_name=target_name) or {
        "versions": [],
        "active": {},
        "errors": [],
        "source": "model_registry",
    }
    versions = list(payload.get("versions") or [])
    if search:
        needle = search.lower()
        versions = [
            item for item in versions
            if needle in str(item.get("model_version") or "").lower()
            or needle in str(item.get("model_name") or "").lower()
        ]
    latest = {str(item.get("model_version")): item for item in versions if item.get("model_version")}
    active = payload.get("active") or {}
    quality_pool = [item for item in versions if _has_quality_metrics(item)]
    active_for_metrics = active
    candidate_pool = [
        item for item in versions
        if str(item.get("status") or "").lower() in {"candidate", "validating", "validated"}
    ]
    candidate_pool.sort(
        key=lambda item: (
            1 if _has_quality_metrics(item) else 0,
            str(item.get("created_at") or item.get("updated_at") or ""),
        ),
        reverse=True,
    )
    candidate = candidate_pool[0] if candidate_pool else {}
    if not _has_quality_metrics(candidate):
        candidate = next((item for item in quality_pool if str(item.get("status") or "").lower() == "candidate"), candidate)
    status_rank = {"candidate": 0, "active": 1, "archived": 2}
    versions.sort(
        key=lambda item: (
            0 if _has_quality_metrics(item) else 1,
            status_rank.get(str(item.get("status") or "").lower(), 3),
            str(item.get("created_at") or item.get("updated_at") or ""),
        )
    )
    active_metrics = latest.get(str(active_for_metrics.get("model_version")), active_for_metrics)
    candidate_metrics = latest.get(str(candidate.get("model_version")), candidate)
    history = _metric_history([str(candidate.get("model_version") or "")], days=30) if candidate else []
    trend_by_date: dict[str, dict[str, Any]] = {}
    for row in history:
        if row.get("model_version") != candidate.get("model_version"):
            continue
        key = str(row.get("metric_date") or "")
        trend_by_date[key] = {
            "date": key[5:] if len(key) >= 10 else key,
            "mae": row.get("mae"),
            "rmse": row.get("rmse"),
            "mape": row.get("mape"),
        }
    rules = [
        {
            "label": "MAE 低于 Active 模型",
            "passed": float(candidate_metrics.get("mae") or 0) < float(active_metrics.get("mae") or 0),
            "detail": f"{candidate_metrics.get('mae', '--')} < {active_metrics.get('mae', '--')}",
        },
        {
            "label": "RMSE 低于 Active 模型",
            "passed": float(candidate_metrics.get("rmse") or 0) < float(active_metrics.get("rmse") or 0),
            "detail": f"{candidate_metrics.get('rmse', '--')} < {active_metrics.get('rmse', '--')}",
        },
        {
            "label": "峰值误差 ≤ 80.00 kW",
            "passed": float(candidate_metrics.get("peak_error") or 9999) <= 80,
            "detail": f"{candidate_metrics.get('peak_error', '--')} ≤ 80.00",
        },
    ]
    summary_rows = [
        {"metric": "MAE (kW)", "active": active_metrics.get("mae"), "candidate": candidate_metrics.get("mae"), "improvement": _improvement(active_metrics, candidate_metrics, "mae")},
        {"metric": "RMSE (kW)", "active": active_metrics.get("rmse"), "candidate": candidate_metrics.get("rmse"), "improvement": _improvement(active_metrics, candidate_metrics, "rmse")},
        {"metric": "MAPE (%)", "active": active_metrics.get("mape"), "candidate": candidate_metrics.get("mape"), "improvement": _improvement(active_metrics, candidate_metrics, "mape")},
        {"metric": "峰值误差 (kW)", "active": active_metrics.get("peak_error"), "candidate": candidate_metrics.get("peak_error"), "improvement": _improvement(active_metrics, candidate_metrics, "peak_error")},
    ]
    effect_points = _prediction_points_from_postgres(
        active_metrics,
        candidate_metrics,
        model_type=effective_model_type,
        region=effective_region,
        days=days,
    ) if active and candidate else []
    return jsonable(
        {
            "available": bool(versions),
            "seed_available": False,
            "empty_state": payload.get("empty_state"),
            "filters": {
                "model_type": effective_model_type,
                "region": effective_region,
                "days": days,
                "domain": domain,
                "target_name": target_name,
            },
            "active": active,
            "candidate": candidate,
            "versions": versions,
            "effect": effect_points,
            "error_trend": list(reversed(list(trend_by_date.values())))[:30],
            "admission": {
                "rules": rules,
                "passed": all(rule["passed"] for rule in rules),
                "conclusion": "满足准入条件" if all(rule["passed"] for rule in rules) else "不满足准入条件",
            },
            "evaluation_summary": summary_rows,
            "training": _training_status(),
            "rollback": {
                "default_version": active.get("model_version"),
                "options": [
                    {
                        "model_version": item.get("model_version"),
                        "label": f"{item.get('model_version')} ({item.get('created_at') or item.get('updated_at')})",
                    }
                    for item in versions
                    if item.get("model_version")
                    and item.get("model_version") != active.get("model_version")
                    and item.get("rollback_eligible")
                ],
            },
            "events": _governance_events(),
            "data_lineage": {
                "versions": "postgresql.model_registry",
                "metrics": "postgresql.model_metrics",
                "effect": "postgresql.model_prediction_comparison_points" if effect_points else "empty",
                "training": "postgresql.task_runs",
                "events": "postgresql.model_governance_events",
                "seed_available": False,
                "source_type": "registry",
            },
        }
    )


def model_version_detail(
    version: str,
    *,
    domain: str = DEFAULT_MODEL_DOMAIN,
    target_name: str = DEFAULT_TARGET_NAME,
) -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "message": "PostgreSQL 不可用"}
    safe_version = str(version or "").strip()
    if not safe_version:
        return {"available": False, "message": "模型版本不能为空"}
    try:
        version_payload = ModelFactService(engine).get_model(safe_version, domain, target_name)
        if not version_payload:
            return {"available": False, "message": "模型不存在或 domain/target 不匹配"}
        with engine.connect() as conn:
            metric_rows = conn.execute(
                text(
                    """
                    SELECT metric_date, mae, rmse, r2, mape, peak_error,
                           sample_count, metrics_json, created_at
                    FROM model_metrics
                    WHERE model_version = :version
                    ORDER BY metric_date DESC NULLS LAST, created_at DESC
                    LIMIT 30
                    """
                ),
                {"version": safe_version},
            ).mappings().all()
            event_rows = conn.execute(
                text(
                    """
                    SELECT event_id, action, target_version, source_version, operator,
                           reason, status, metadata_json, created_at
                    FROM model_governance_events
                    WHERE target_version = :version OR source_version = :version
                    ORDER BY created_at DESC, id DESC
                    LIMIT 20
                    """
                ),
                {"version": safe_version},
            ).mappings().all()
            prediction_rows = conn.execute(
                text(
                    """
                    SELECT forecast_time, actual_value, active_prediction,
                           candidate_prediction, diff_value, active_version,
                           candidate_version, data_origin
                    FROM model_prediction_comparison_points
                    WHERE active_version = :version OR candidate_version = :version
                    ORDER BY forecast_time
                    LIMIT 24
                    """
                ),
                {"version": safe_version},
            ).mappings().all()
    except Exception:
        return {"available": False, "message": "模型详情读取失败"}

    version_payload["metrics"] = {
        key: version_payload.get(key)
        for key in ("test_mae", "test_rmse", "peak_rmse", "spike_rmse", "rolling_rmse")
        if version_payload.get(key) is not None
    }
    metrics_history = mapping_list(metric_rows)
    for item in metrics_history:
        item["metrics"] = loads_json(item.pop("metrics_json", None), default={})
    events = mapping_list(event_rows)
    for item in events:
        item["metadata"] = loads_json(item.pop("metadata_json", None), default={})
    prediction_samples = []
    for item in mapping_list(prediction_rows):
        prediction_samples.append(
            {
                **item,
                "time": _chart_time(item.get("forecast_time")),
            }
        )
    return jsonable(
        {
            "available": True,
            "version": version_payload,
            "latest_metric": metrics_history[0] if metrics_history else {},
            "metrics_history": metrics_history,
            "events": events,
            "prediction_samples": prediction_samples,
            "data_lineage": {
                "version": "postgresql.model_registry",
                "metrics": "postgresql.model_metrics",
                "events": "postgresql.model_governance_events",
                "prediction_samples": "postgresql.model_prediction_comparison_points",
                "source_type": "registry",
            },
        }
    )


def record_model_event(
    *,
    action: str,
    target_version: str,
    source_version: str = "",
    user: CurrentUser | None = None,
    reason: str = "",
    status: str = "success",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    engine = postgres_engine()
    event_id = f"mge_{uuid4().hex[:16]}"
    if engine is None:
        return {"available": False, "event_id": event_id}
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO model_governance_events (
                        event_id, action, target_version, source_version, operator,
                        reason, status, metadata_json, created_at
                    )
                    VALUES (
                        :event_id, :action, :target_version, :source_version, :operator,
                        :reason, :status, CAST(:metadata_json AS jsonb), CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "event_id": event_id,
                    "action": action,
                    "target_version": target_version,
                    "source_version": source_version,
                    "operator": user.username if user else "",
                    "reason": reason,
                    "status": status,
                    "metadata_json": dumps_json(metadata or {}),
                },
            )
        return {"available": True, "event_id": event_id}
    except Exception:
        return {"available": False, "event_id": event_id}


def start_model_training(user: CurrentUser | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    engine = postgres_engine()
    task_id = f"train_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:4]}"
    metadata = {"trigger": "model_center", **(payload or {})}
    if engine is not None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO task_runs (
                        task_id, run_id, task_name, task_kind, status, payload_json,
                        created_at, updated_at
                    )
                    VALUES (
                        :task_id, :task_id, '模型中心手动训练', 'retrain_model', 'pending',
                        CAST(:payload AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (task_id) DO NOTHING
                    """
                ),
                {"task_id": task_id, "payload": dumps_json(metadata)},
            )
        try:
            from .task_repository import append_task_log

            append_task_log(
                task_id,
                level="info",
                step="submit",
                message="模型训练任务已提交，等待训练执行器调度。",
                status="pending",
                task_name="模型中心手动训练",
                task_kind="retrain_model",
                metadata=metadata,
                sequence_no=1,
            )
        except Exception:
            pass
    event = record_model_event(action="training.start", target_version="", user=user, reason="用户从模型中心启动训练", metadata=metadata)
    return {"task_id": task_id, "status": "pending", "event": event}


def activate_model_version(
    version: str,
    user: CurrentUser | None = None,
    reason: str = "",
    *,
    domain: str = DEFAULT_MODEL_DOMAIN,
    target_name: str = DEFAULT_TARGET_NAME,
) -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"success": False, "message": "PostgreSQL 不可用"}
    service = ModelFactService(engine)
    current = service.get_active_model(domain, target_name)
    try:
        active = service.activate_model(version, domain, target_name)
    except ModelFactError as exc:
        return {"success": False, "message": str(exc)}
    event = record_model_event(
        action="model.activate",
        target_version=version,
        source_version=str(current.get("model_version") or ""),
        user=user,
        reason=reason,
        metadata={"domain": domain, "target_name": target_name, "source_type": "registry"},
    )
    return {
        "success": True,
        "active_version": active.get("model_version"),
        "previous_active_version": current.get("model_version") or "",
        "domain": domain,
        "target_name": target_name,
        "event": event,
    }


def rollback_model_version(
    version: str,
    user: CurrentUser | None = None,
    reason: str = "",
    *,
    domain: str = DEFAULT_MODEL_DOMAIN,
    target_name: str = DEFAULT_TARGET_NAME,
) -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"success": False, "message": "PostgreSQL 不可用"}
    service = ModelFactService(engine)
    current = service.get_active_model(domain, target_name)
    try:
        active = service.rollback_active_model(version, domain, target_name)
    except ModelFactError as exc:
        return {"success": False, "message": str(exc)}
    event = record_model_event(
        action="model.rollback",
        target_version=version,
        source_version=str(current.get("model_version") or ""),
        user=user,
        reason=reason or "模型中心回滚操作",
        metadata={"domain": domain, "target_name": target_name, "source_type": "registry"},
    )
    return {
        "success": True,
        "active_version": active.get("model_version"),
        "previous_active_version": current.get("model_version") or "",
        "domain": domain,
        "target_name": target_name,
        "event": event,
    }

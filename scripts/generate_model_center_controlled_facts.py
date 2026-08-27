from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config_loader import load_dotenv


DEFAULT_BATCH_ID = "model-center-ui-20260827-v1"
SCENARIO = "model_center_ui_capacity_preview"
DATA_SOURCE = "controlled_generation"
HISTORICAL_VERSION_COUNT = 8
METRIC_DAYS = 30
COMPARISON_DAYS = 7
POINTS_PER_DAY = 96


def _metadata(batch_id: str, generated_at: datetime) -> dict[str, Any]:
    return {
        "data_source": DATA_SOURCE,
        "source_type": DATA_SOURCE,
        "is_simulated": True,
        "batch_id": batch_id,
        "generated_at": generated_at.isoformat(),
        "scenario": SCENARIO,
    }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def _batch_counts(conn: Any, batch_id: str) -> dict[str, int]:
    params = {"batch_id": batch_id}
    queries = {
        "registry": "SELECT COUNT(*) FROM model_registry WHERE metadata_json ->> 'batch_id' = :batch_id",
        "metrics": "SELECT COUNT(*) FROM model_metrics WHERE metrics_json ->> 'batch_id' = :batch_id",
        "comparison": "SELECT COUNT(*) FROM model_prediction_comparison_points WHERE metadata_json ->> 'batch_id' = :batch_id",
        "events": "SELECT COUNT(*) FROM model_governance_events WHERE metadata_json ->> 'batch_id' = :batch_id",
        "task_logs": "SELECT COUNT(*) FROM task_logs WHERE metadata_json ->> 'batch_id' = :batch_id",
        "tasks": "SELECT COUNT(*) FROM task_runs WHERE metadata_json ->> 'batch_id' = :batch_id",
    }
    return {name: int(conn.execute(text(sql), params).scalar() or 0) for name, sql in queries.items()}


def _expected_counts() -> dict[str, int]:
    return {
        "registry": HISTORICAL_VERSION_COUNT,
        "metrics": METRIC_DAYS * 2 + HISTORICAL_VERSION_COUNT,
        "comparison": COMPARISON_DAYS * POINTS_PER_DAY,
        "events": 2,
        "task_logs": 4,
        "tasks": 1,
    }


def _select_model_pair(conn: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            SELECT model_id, model_version, status, is_active, test_mae, test_rmse,
                   peak_rmse, created_at, validated_at
            FROM model_registry
            WHERE domain = 'price' AND target_name = 'da_price'
              AND COALESCE(metadata_json ->> 'batch_id', '') = ''
            ORDER BY is_active DESC, created_at DESC
            """
        )
    ).mappings().all()
    active = next((dict(row) for row in rows if bool(row["is_active"]) and str(row["status"]).lower() == "active"), None)
    candidate = next(
        (dict(row) for row in rows if str(row["status"]).lower() in {"candidate", "validating", "validated"}),
        None,
    )
    if not active or not candidate:
        raise RuntimeError("缺少 price/da_price 的 Active 或 Candidate；拒绝生成模型中心受控数据")
    return active, candidate


def _metric_values(base_mae: float, base_rmse: float, base_peak: float, days_back: int, phase: float) -> dict[str, float]:
    ratio = days_back / max(METRIC_DAYS - 1, 1)
    wobble = math.sin(days_back * 0.82 + phase)
    return {
        "mae": round(base_mae * (1 + ratio * 0.09) + wobble * 0.38, 2),
        "rmse": round(base_rmse * (1 + ratio * 0.08) + wobble * 0.62, 2),
        "mape": round(max(1.0, base_mae / 5.25) * (1 + ratio * 0.06) + wobble * 0.08, 2),
        "peak_error": round(base_peak * (1 + ratio * 0.07) + wobble * 0.55, 2),
    }


def _insert_historical_versions(conn: Any, *, batch_id: str, generated_at: datetime, as_of: date, active: dict[str, Any]) -> list[dict[str, Any]]:
    audit = _metadata(batch_id, generated_at)
    versions: list[dict[str, Any]] = []
    active_mae = float(active.get("test_mae") or 16.1)
    active_rmse = float(active.get("test_rmse") or 32.7)
    active_peak = float(active.get("peak_rmse") or 31.2)
    for index in range(HISTORICAL_VERSION_COUNT):
        trained_on = as_of - timedelta(days=31 * (index + 1))
        version = f"price_archive_{trained_on:%Y%m%d}_r{HISTORICAL_VERSION_COUNT - index}"
        model_id = f"controlled-{hashlib.sha256((batch_id + version).encode()).hexdigest()[:20]}"
        scale = 1.05 + index * 0.045
        row = {
            "model_id": model_id,
            "model_version": version,
            "trained_on": trained_on,
            "test_mae": round(active_mae * scale, 6),
            "test_rmse": round(active_rmse * scale, 6),
            "peak_rmse": round(active_peak * (scale + 0.025), 6),
            "metadata_json": _json({**audit, "record_kind": "historical_model_version"}),
        }
        conn.execute(
            text(
                """
                INSERT INTO model_registry (
                    model_id, model_version, domain, target_name, model_role,
                    artifact_id, artifact_path, artifact_hash, feature_version, schema_hash,
                    status, is_active, source_type, train_start_date, train_end_date,
                    test_mae, test_rmse, peak_rmse, spike_rmse, rolling_rmse,
                    created_at, validated_at, metadata_json
                ) VALUES (
                    :model_id, :model_version, 'price', 'da_price', 'price',
                    :model_version, :artifact_path, :artifact_hash, 'features_price_history_v1', :schema_hash,
                    'archived', 0, :source_type, :train_start, :train_end,
                    :test_mae, :test_rmse, :peak_rmse, :spike_rmse, :rolling_rmse,
                    :created_at, NULL, CAST(:metadata_json AS jsonb)
                )
                """
            ),
            {
                **row,
                "artifact_path": f"model_artifacts/price_history/{version}",
                "artifact_hash": hashlib.sha256(f"artifact:{version}".encode()).hexdigest(),
                "schema_hash": hashlib.sha256(b"price-history-schema-v1").hexdigest(),
                "source_type": DATA_SOURCE,
                "train_start": trained_on - timedelta(days=180),
                "train_end": trained_on - timedelta(days=1),
                "spike_rmse": round(active_peak * (scale + 0.06), 6),
                "rolling_rmse": round(active_rmse * (scale + 0.015), 6),
                "created_at": datetime.combine(trained_on, time(21, 30)),
            },
        )
        versions.append(row)
    return versions


def _insert_metrics(
    conn: Any,
    *,
    batch_id: str,
    generated_at: datetime,
    as_of: date,
    active: dict[str, Any],
    candidate: dict[str, Any],
    historical: list[dict[str, Any]],
) -> None:
    audit = _metadata(batch_id, generated_at)
    for phase, model in enumerate((active, candidate)):
        base_mae = float(model.get("test_mae") or (16.1 if phase == 0 else 18.4))
        base_rmse = float(model.get("test_rmse") or (32.7 if phase == 0 else 38.2))
        base_peak = float(model.get("peak_rmse") or (31.2 if phase == 0 else 42.5))
        for days_back in range(METRIC_DAYS):
            values = _metric_values(base_mae, base_rmse, base_peak, days_back, phase * 0.7)
            conn.execute(
                text(
                    """
                    INSERT INTO model_metrics (
                        model_version, metric_date, mae, rmse, r2, mape,
                        peak_error, sample_count, metrics_json, created_at
                    ) VALUES (
                        :model_version, :metric_date, :mae, :rmse, :r2, :mape,
                        :peak_error, :sample_count, CAST(:metrics_json AS jsonb), :created_at
                    )
                    """
                ),
                {
                    "model_version": model["model_version"],
                    "metric_date": as_of - timedelta(days=days_back),
                    **values,
                    "r2": round(0.91 - phase * 0.08 - days_back * 0.0008, 4),
                    "sample_count": 2688,
                    "metrics_json": _json({**audit, "record_kind": "daily_model_metric"}),
                    "created_at": datetime.combine(as_of - timedelta(days=days_back), time(23, 10)),
                },
            )
    for index, item in enumerate(historical):
        conn.execute(
            text(
                """
                INSERT INTO model_metrics (
                    model_version, metric_date, mae, rmse, r2, mape,
                    peak_error, sample_count, metrics_json, created_at
                ) VALUES (
                    :model_version, :metric_date, :mae, :rmse, :r2, :mape,
                    :peak_error, :sample_count, CAST(:metrics_json AS jsonb), :created_at
                )
                """
            ),
            {
                "model_version": item["model_version"],
                "metric_date": item["trained_on"],
                "mae": item["test_mae"],
                "rmse": item["test_rmse"],
                "r2": round(0.88 - index * 0.012, 4),
                "mape": round(float(item["test_mae"]) / 5.2, 2),
                "peak_error": item["peak_rmse"],
                "sample_count": 8064 + index * 672,
                "metrics_json": _json({**audit, "record_kind": "historical_model_metric"}),
                "created_at": datetime.combine(item["trained_on"], time(22, 0)),
            },
        )


def _insert_comparison_points(conn: Any, *, batch_id: str, generated_at: datetime, as_of: date, active: dict[str, Any], candidate: dict[str, Any]) -> None:
    audit = _metadata(batch_id, generated_at)
    active_mae = float(active.get("test_mae") or 16.1)
    candidate_mae = float(candidate.get("test_mae") or 45.6)
    start_at = datetime.combine(as_of - timedelta(days=COMPARISON_DAYS - 1), time.min)
    for index in range(COMPARISON_DAYS * POINTS_PER_DAY):
        forecast_time = start_at + timedelta(minutes=15 * index)
        hour = forecast_time.hour + forecast_time.minute / 60
        morning = math.exp(-((hour - 10.0) ** 2) / 9.5)
        evening = math.exp(-((hour - 19.0) ** 2) / 7.0)
        actual = 418 + 106 * morning + 148 * evening + 19 * math.sin(index / 17) + (forecast_time.weekday() < 5) * 24
        active_error = active_mae * (0.72 * math.sin(index / 5.4) + 0.34 * math.cos(index / 13.0))
        candidate_error = candidate_mae * (0.66 * math.sin(index / 5.8 + 0.3) + 0.28 * math.cos(index / 11.0))
        active_prediction = actual + active_error
        candidate_prediction = actual + candidate_error
        conn.execute(
            text(
                """
                INSERT INTO model_prediction_comparison_points (
                    model_type, region, forecast_time, active_version, candidate_version,
                    actual_value, active_prediction, candidate_prediction, diff_value,
                    granularity, data_origin, metadata_json, created_at, updated_at
                ) VALUES (
                    '负荷预测模型', '浙江省', :forecast_time, :active_version, :candidate_version,
                    :actual_value, :active_prediction, :candidate_prediction, :diff_value,
                    '15分钟', :data_origin, CAST(:metadata_json AS jsonb), :created_at, :created_at
                )
                """
            ),
            {
                "forecast_time": forecast_time,
                "active_version": active["model_version"],
                "candidate_version": candidate["model_version"],
                "actual_value": round(actual, 3),
                "active_prediction": round(active_prediction, 3),
                "candidate_prediction": round(candidate_prediction, 3),
                "diff_value": round(abs(candidate_error) - abs(active_error), 3),
                "data_origin": DATA_SOURCE,
                "metadata_json": _json({**audit, "record_kind": "prediction_comparison_point"}),
                "created_at": generated_at.replace(tzinfo=None),
            },
        )


def _insert_training_and_events(conn: Any, *, batch_id: str, generated_at: datetime, as_of: date, active: dict[str, Any], candidate: dict[str, Any]) -> None:
    audit = _metadata(batch_id, generated_at)
    task_id = "train_model_center_preview_20260801"
    started_at = datetime.combine(as_of, time(9, 12))
    ended_at = started_at + timedelta(minutes=32, seconds=41)
    conn.execute(
        text(
            """
            INSERT INTO task_runs (
                task_id, run_id, task_name, task_kind, status, payload_json,
                started_at, ended_at, duration_seconds, created_at, updated_at, metadata_json
            ) VALUES (
                :task_id, :task_id, '候选模型评估训练', 'retrain_model', 'success', CAST(:payload AS jsonb),
                :started_at, :ended_at, :duration_seconds, :started_at, :ended_at, CAST(:metadata AS jsonb)
            )
            """
        ),
        {
            "task_id": task_id,
            "payload": _json({**audit, "candidate_model_version": candidate["model_version"], "sample_count": 1892743}),
            "metadata": _json({**audit, "record_kind": "training_task"}),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": 1961,
        },
    )
    log_rows = [
        ("prepare", "训练样本窗口与字段契约检查完成", 18, started_at + timedelta(minutes=4)),
        ("train", "候选模型训练完成，已生成模型评估结果", 72, started_at + timedelta(minutes=24)),
        ("evaluate", "30 天误差趋势与高峰时段指标计算完成", 92, ended_at - timedelta(minutes=3)),
        ("complete", "训练任务成功结束，等待人工准入复核", 100, ended_at),
    ]
    for sequence_no, (step, message, progress, created_at) in enumerate(log_rows, start=1):
        conn.execute(
            text(
                """
                INSERT INTO task_logs (
                    task_id, run_id, task_name, task_kind, status,
                    log_text, progress, message, metadata_json,
                    level, step, sequence_no, created_at, updated_at
                ) VALUES (
                    :task_id, :task_id, '候选模型评估训练', 'retrain_model', 'success',
                    :message, :progress, :message, CAST(:metadata AS jsonb),
                    'info', :step, :sequence_no, :created_at, :created_at
                )
                """
            ),
            {
                "task_id": task_id,
                "message": message,
                "progress": progress,
                "metadata": _json({**audit, "record_kind": "training_task_log"}),
                "step": step,
                "sequence_no": sequence_no,
                "created_at": created_at,
            },
        )
    events = [
        ("training.completed", candidate["model_version"], "", "候选模型训练与评估已完成", ended_at),
        ("admission.evaluated", candidate["model_version"], active["model_version"], "候选模型已完成准入规则评估", ended_at + timedelta(minutes=2)),
    ]
    for index, (action, target, source, reason, created_at) in enumerate(events, start=1):
        conn.execute(
            text(
                """
                INSERT INTO model_governance_events (
                    event_id, action, target_version, source_version, operator,
                    reason, status, metadata_json, created_at
                ) VALUES (
                    :event_id, :action, :target, :source, 'system',
                    :reason, 'success', CAST(:metadata AS jsonb), :created_at
                )
                """
            ),
            {
                "event_id": f"mge_{batch_id}_{index}",
                "action": action,
                "target": target,
                "source": source,
                "reason": reason,
                "metadata": _json({**audit, "record_kind": "governance_event"}),
                "created_at": created_at,
            },
        )


def apply_batch(engine: Engine, batch_id: str = DEFAULT_BATCH_ID) -> dict[str, Any]:
    expected = _expected_counts()
    generated_at = datetime(2026, 8, 1, 23, 0, tzinfo=timezone(timedelta(hours=8)))
    with engine.begin() as conn:
        before = _batch_counts(conn, batch_id)
        if before == expected:
            return {"status": "already_applied", "batch_id": batch_id, "counts": before}
        if any(before.values()):
            raise RuntimeError(f"批次 {batch_id} 存在不完整数据 {before}；请先按批次回滚，拒绝覆盖")
        active, candidate = _select_model_pair(conn)
        as_of = min(date(2026, 8, 1), date.fromisoformat(str(candidate["created_at"])[:10]))
        historical = _insert_historical_versions(conn, batch_id=batch_id, generated_at=generated_at, as_of=as_of, active=active)
        _insert_metrics(conn, batch_id=batch_id, generated_at=generated_at, as_of=as_of, active=active, candidate=candidate, historical=historical)
        _insert_comparison_points(conn, batch_id=batch_id, generated_at=generated_at, as_of=as_of, active=active, candidate=candidate)
        _insert_training_and_events(conn, batch_id=batch_id, generated_at=generated_at, as_of=as_of, active=active, candidate=candidate)
        after = _batch_counts(conn, batch_id)
        if after != expected:
            raise RuntimeError(f"受控数据写入计数不完整：expected={expected}, actual={after}")
    return {"status": "applied", "batch_id": batch_id, "counts": after}


def rollback_batch(engine: Engine, batch_id: str = DEFAULT_BATCH_ID) -> dict[str, Any]:
    params = {"batch_id": batch_id}
    with engine.begin() as conn:
        before = _batch_counts(conn, batch_id)
        conn.execute(text("DELETE FROM model_prediction_comparison_points WHERE metadata_json ->> 'batch_id' = :batch_id"), params)
        conn.execute(text("DELETE FROM model_metrics WHERE metrics_json ->> 'batch_id' = :batch_id"), params)
        conn.execute(text("DELETE FROM model_governance_events WHERE metadata_json ->> 'batch_id' = :batch_id"), params)
        conn.execute(text("DELETE FROM task_logs WHERE metadata_json ->> 'batch_id' = :batch_id"), params)
        conn.execute(text("DELETE FROM task_runs WHERE metadata_json ->> 'batch_id' = :batch_id"), params)
        conn.execute(text("DELETE FROM model_registry WHERE metadata_json ->> 'batch_id' = :batch_id"), params)
        after = _batch_counts(conn, batch_id)
        if any(after.values()):
            raise RuntimeError(f"批次回滚不完整：{after}")
    return {"status": "rolled_back", "batch_id": batch_id, "removed": before, "counts": after}


def batch_status(engine: Engine, batch_id: str = DEFAULT_BATCH_ID) -> dict[str, Any]:
    with engine.connect() as conn:
        counts = _batch_counts(conn, batch_id)
        active = conn.execute(text("SELECT model_version FROM model_registry WHERE domain='price' AND target_name='da_price' AND status='active' AND is_active=1")).scalar()
    return {"status": "present" if any(counts.values()) else "absent", "batch_id": batch_id, "counts": counts, "active_version": active}


def _engine_from_env(env_file: Path) -> Engine:
    load_dotenv(env_file)
    database_url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    parsed = urlsplit(database_url)
    if not (
        parsed.hostname in {"localhost", "127.0.0.1"}
        and (parsed.port or 5432) == 5432
        and parsed.path.lstrip("/") == "postgres"
        and parsed.username == "postgres"
    ):
        raise RuntimeError("数据库目标必须是 localhost:5432/postgres 且用户必须是 postgres")
    return create_engine(database_url, future=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="模型中心受控展示数据生成与批次回滚")
    parser.add_argument("command", choices=("apply", "status", "rollback"))
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    parser.add_argument("--env-file", type=Path, default=Path(__file__).resolve().parents[1] / ".env")
    args = parser.parse_args()
    engine = _engine_from_env(args.env_file)
    try:
        if args.command == "apply":
            result = apply_batch(engine, args.batch_id)
        elif args.command == "rollback":
            result = rollback_batch(engine, args.batch_id)
        else:
            result = batch_status(engine, args.batch_id)
        print(_json(result))
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from backend.app.repositories.base import dumps_json, postgres_engine
from backend.app.repositories.task_repository import save_task_record


TASK_SEEDS = [
    ("seed_task_price_15min", "电价预测_15min_全量", "price_predict", "price_predict", "success", 100, 0, ""),
    ("seed_task_load_daily", "负荷预测_日度_全量", "load_predict", "load_predict", "running", 68, 0, ""),
    ("seed_task_strategy_daily", "交易策略生成_日前", "strategy_gen", "strategy_gen", "queued", 0, 0, ""),
    ("seed_task_report_daily", "收益分析_日报", "report_daily", "report_daily", "success", 100, 0, ""),
    ("seed_task_monitor_rt", "异常监测_实时", "monitor_rt", "monitor_rt", "running", 96, 1, ""),
    ("seed_task_data_sync_a", "数据同步_源站点A", "sync_core_data", "data_sync", "failed", 0, 2, "数据库连接超时"),
    ("seed_task_model_train", "模型训练_电价模型", "model_train", "model_train", "success", 100, 0, ""),
    ("seed_task_data_clean", "数据清洗_全量", "data_clean", "data_clean", "timeout", 26, 3, "执行超时"),
    ("seed_task_runtime_check", "runtime_check", "health_check", "default", "cancelled", 100, 0, "人工取消巡检"),
]


LOG_MESSAGES = {
    "success": [("info", "prepare", "任务开始执行"), ("info", "execute", "任务执行完成")],
    "running": [("info", "prepare", "任务开始执行"), ("info", "execute", "任务执行中，进度已更新")],
    "queued": [("info", "prepare", "任务已进入队列，等待 worker 执行")],
    "failed": [("info", "prepare", "任务开始执行"), ("error", "execute", "数据库连接失败，请检查连接配置")],
    "timeout": [("info", "prepare", "任务开始执行"), ("error", "execute", "任务执行超时，建议优化数据量或延长超时时间")],
    "cancelled": [("warning", "cleanup", "任务已取消，等待重新提交")],
}


def _record(row: tuple, index: int) -> dict:
    task_id, task_name, kind, queue_name, status, progress, retry_count, error_message = row
    created = datetime.now() - timedelta(hours=index * 3, days=index % 4)
    started = created + timedelta(minutes=1)
    ended = None if status in {"running", "queued", "pending"} else started + timedelta(minutes=12 + index)
    return {
        "task_id": task_id,
        "run_id": created.strftime("%Y%m%d_%H%M%S"),
        "kind": kind,
        "task_name": task_name,
        "task_type": kind,
        "status": status,
        "payload": {"market": "浙江省", "seed_source": "task_center_business_seed"},
        "created_at": created,
        "queued_at": created,
        "started_at": started if status != "queued" else None,
        "ended_at": ended,
        "finished_at": ended,
        "duration_seconds": None if ended is None else round((ended - started).total_seconds(), 3),
        "error_message": error_message,
        "error_code": "TASK_TIMEOUT" if status == "timeout" else ("TASK_FAILED" if status == "failed" else ""),
        "error_detail": error_message,
        "progress": progress,
        "message": status,
        "created_by": "seed",
        "retry_count": retry_count,
        "max_retries": 3,
        "execution_mode": "scheduled" if kind not in {"health_check"} else "manual",
        "queue_name": queue_name,
        "worker_id": f"worker-{(index % 4) + 1:02d}",
        "celery_task_id": f"celery-seed-{task_id[-8:]}",
        "metadata": {"business_domain": "power_trading_task_center"},
    }


def _fix_timestamps(engine, record: dict) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE task_runs
                SET created_at = :created_at,
                    updated_at = :updated_at,
                    queued_at = :queued_at,
                    started_at = :started_at,
                    ended_at = :ended_at,
                    finished_at = :finished_at
                WHERE task_id = :task_id
                """
            ),
            {
                "task_id": record["task_id"],
                "created_at": record["created_at"],
                "updated_at": record["ended_at"] or datetime.now(),
                "queued_at": record["queued_at"],
                "started_at": record["started_at"],
                "ended_at": record["ended_at"],
                "finished_at": record["finished_at"],
            },
        )


def _seed_logs(engine, record: dict) -> int:
    with engine.begin() as conn:
        existing = int(
            conn.execute(
                text("SELECT COUNT(*) FROM task_logs WHERE task_id = :task_id AND COALESCE(sequence_no, 0) > 0"),
                {"task_id": record["task_id"]},
            ).scalar()
            or 0
        )
        if existing:
            return 0
        rows = LOG_MESSAGES.get(record["status"], LOG_MESSAGES["running"])
        for index, (level, step, message) in enumerate(rows, start=1):
            conn.execute(
                text(
                    """
                    INSERT INTO task_logs (
                        task_id, run_id, task_name, task_kind, status, command_json,
                        log_text, started_at, ended_at, duration_seconds, returncode,
                        error_message, progress, message, result_ref, metadata_json,
                        execution_mode, worker_id, celery_task_id, level, step,
                        sequence_no, created_at, updated_at
                    )
                    VALUES (
                        :task_id, :run_id, :task_name, :task_kind, :status,
                        CAST(:command_json AS jsonb), :log_text, :started_at,
                        :ended_at, :duration_seconds, :returncode, :error_message,
                        :progress, :message, :result_ref, CAST(:metadata_json AS jsonb),
                        :execution_mode, :worker_id, :celery_task_id, :level, :step,
                        :sequence_no, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "task_id": record["task_id"],
                    "run_id": record["run_id"],
                    "task_name": record["task_name"],
                    "task_kind": record["kind"],
                    "status": record["status"],
                    "command_json": dumps_json([]),
                    "log_text": message,
                    "started_at": record["started_at"],
                    "ended_at": record["ended_at"],
                    "duration_seconds": record["duration_seconds"],
                    "returncode": 0 if record["status"] == "success" else None,
                    "error_message": record["error_message"],
                    "progress": record["progress"],
                    "message": message,
                    "result_ref": record.get("result_ref") or "",
                    "metadata_json": dumps_json(record["metadata"]),
                    "execution_mode": record["execution_mode"],
                    "worker_id": record["worker_id"],
                    "celery_task_id": record["celery_task_id"],
                    "level": level,
                    "step": step,
                    "sequence_no": index,
                    "created_at": record["created_at"] + timedelta(minutes=index),
                    "updated_at": record["created_at"] + timedelta(minutes=index),
                },
            )
    return len(LOG_MESSAGES.get(record["status"], []))


def main() -> int:
    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL is required, for example: postgresql+psycopg2://postgres:***@localhost:5432/postgres")
        return 2
    engine = postgres_engine()
    if engine is None:
        print("PostgreSQL engine is unavailable. Run alembic upgrade head and check DATABASE_URL.")
        return 3
    saved = 0
    logs = 0
    for index, row in enumerate(TASK_SEEDS):
        record = _record(row, index)
        if save_task_record(record, status=record["status"], log_text=record["message"]):
            _fix_timestamps(engine, record)
            logs += _seed_logs(engine, record)
            saved += 1
    print(f"seeded task center records: task_runs={saved}, task_logs_inserted={logs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

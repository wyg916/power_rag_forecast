from __future__ import annotations

from typing import Any

from sqlalchemy import text

from database_utils import apply_database_migrations, create_database_engine, get_database_config, now_text


def create_retrain_job(
    config: dict[str, Any],
    trigger_reason: str,
    trigger_source: str = "monitor",
    status: str = "pending",
    log=None,
) -> str | None:
    if not get_database_config(config).enabled:
        if log:
            log("数据库未启用，跳过重训任务登记。")
        return None

    apply_database_migrations(config, log=log)
    job_id = "retrain_" + now_text("%Y%m%d_%H%M%S")
    engine = create_database_engine(config)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO model_retrain_jobs (
                    job_id, trigger_source, trigger_reason, status, requested_at
                )
                VALUES (:job_id, :trigger_source, :trigger_reason, :status, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE
                    trigger_reason = VALUES(trigger_reason),
                    status = VALUES(status)
                """
            ),
            {
                "job_id": job_id,
                "trigger_source": trigger_source,
                "trigger_reason": trigger_reason,
                "status": status,
            },
        )
    if log:
        log(f"已登记候选模型重训任务：{job_id}")
    return job_id

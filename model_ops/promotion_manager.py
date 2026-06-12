from __future__ import annotations

from typing import Any

from sqlalchemy import text

from database_utils import apply_database_migrations, create_database_engine, get_database_config


def promote_to_active(config: dict[str, Any], model_version: str, approved_by: str = "system", log=None) -> bool:
    if not get_database_config(config).enabled:
        if log:
            log("数据库未启用，跳过模型上线。")
        return False

    apply_database_migrations(config, log=log)
    engine = create_database_engine(config)
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT COUNT(*) FROM model_registry WHERE model_version = :model_version"),
            {"model_version": model_version},
        ).scalar()
        if not exists:
            raise ValueError(f"模型版本不存在：{model_version}")
        conn.execute(text("UPDATE model_registry SET is_active = 0 WHERE is_active = 1"))
        conn.execute(
            text(
                """
                UPDATE model_registry
                SET is_active = 1,
                    status = 'active',
                    activated_at = CURRENT_TIMESTAMP
                WHERE model_version = :model_version
                """
            ),
            {"model_version": model_version},
        )
        conn.execute(
            text(
                """
                INSERT INTO audit_logs (actor, action, target_type, target_id, details, created_at)
                VALUES (:actor, 'promote_model', 'model_registry', :target_id, :details, CURRENT_TIMESTAMP)
                """
            ),
            {"actor": approved_by, "target_id": model_version, "details": f"Promoted {model_version} to active"},
        )
    if log:
        log(f"模型已上线为 active：{model_version}")
    return True


def get_latest_candidate_version(config: dict[str, Any]) -> str | None:
    if not get_database_config(config).enabled:
        return None
    apply_database_migrations(config)
    engine = create_database_engine(config)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT model_version
                FROM model_registry
                WHERE status = 'candidate'
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
        ).mappings().fetchone()
    return str(row["model_version"]) if row else None

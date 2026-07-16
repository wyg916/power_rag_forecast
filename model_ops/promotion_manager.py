from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.app.services.model_fact_service import DEFAULT_MODEL_DOMAIN, DEFAULT_TARGET_NAME, ModelFactError, ModelFactService
from database_utils import create_database_engine, get_database_config


def promote_to_active(config: dict[str, Any], model_version: str, approved_by: str = "system", log=None) -> bool:
    if not get_database_config(config).enabled:
        if log:
            log("数据库未启用，跳过模型上线。")
        return False

    actor = str(approved_by or "").strip()
    if actor.lower() in {"", "system", "auto", "automatic"}:
        raise ModelFactError("模型激活必须记录明确的人工批准人")
    engine = create_database_engine(config)
    model_cfg = config.get("model_learning", {}) or {}
    domain = str(model_cfg.get("domain") or DEFAULT_MODEL_DOMAIN).strip().lower()
    target_name = str(model_cfg.get("target_name") or DEFAULT_TARGET_NAME).strip()
    active = ModelFactService(engine).activate_model(model_version, domain, target_name)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO audit_logs (actor, action, target_type, target_id, details, created_at)
                VALUES (:actor, 'promote_model', 'model_registry', :target_id, :details, CURRENT_TIMESTAMP)
                """
            ),
            {
                "actor": actor,
                "target_id": model_version,
                "details": f"Promoted {model_version} to active for {domain}/{target_name}",
            },
        )
    if log:
        log(f"模型已上线为 active：{active.get('model_version')}")
    return bool(active.get("is_active"))


def get_latest_candidate_version(config: dict[str, Any]) -> str | None:
    if not get_database_config(config).enabled:
        return None
    model_cfg = config.get("model_learning", {}) or {}
    domain = str(model_cfg.get("domain") or DEFAULT_MODEL_DOMAIN).strip().lower()
    target_name = str(model_cfg.get("target_name") or DEFAULT_TARGET_NAME).strip()
    rows = ModelFactService(create_database_engine(config)).list_models(domain, target_name)
    candidate = next((row for row in rows if row.get("status") == "candidate"), None)
    return str(candidate["model_version"]) if candidate else None

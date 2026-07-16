from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine


MODEL_STATES = frozenset({"candidate", "validating", "validated", "active", "rejected", "archived"})
DEFAULT_MODEL_DOMAIN = "price"
DEFAULT_TARGET_NAME = "da_price"

_MODEL_COLUMNS = """
    model_id, model_version, domain, target_name, model_role,
    artifact_id, artifact_path, artifact_hash, feature_version, schema_hash,
    status, is_active, source_type, train_start_date, train_end_date,
    test_mae, test_rmse, peak_rmse, spike_rmse, rolling_rmse,
    created_at, validated_at, activated_at, deactivated_at
"""


class ModelFactError(RuntimeError):
    """Raised when a model lifecycle operation violates the fact contract."""


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _fact(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    item = _jsonable(dict(row))
    item["status"] = str(item.get("status") or "").strip().lower()
    item["is_active"] = bool(item.get("is_active")) and item["status"] == "active"
    item["source_type"] = str(item.get("source_type") or "registry")
    return item


def _scope(domain: str, target_name: str) -> tuple[str, str]:
    safe_domain = str(domain or "").strip().lower()
    safe_target = str(target_name or "").strip()
    if not safe_domain or not safe_target:
        raise ModelFactError("domain 和 target_name 必须明确提供")
    return safe_domain, safe_target


class ModelFactService:
    """Single read/write boundary for model_registry.

    Read methods only use ``engine.connect()`` and never run migrations, seed,
    status changes, or cross-table fallbacks. Lifecycle writes are explicit and
    transactional.
    """

    def __init__(self, engine: Engine | None):
        self.engine = engine

    def list_models(self, domain: str, target_name: str) -> list[dict[str, Any]]:
        safe_domain, safe_target = _scope(domain, target_name)
        if self.engine is None:
            return []
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT {_MODEL_COLUMNS}
                    FROM model_registry
                    WHERE domain = :domain AND target_name = :target_name
                    ORDER BY CASE WHEN LOWER(status) = 'active' AND is_active = 1 THEN 0 ELSE 1 END,
                             created_at DESC, model_version DESC
                    """
                ),
                {"domain": safe_domain, "target_name": safe_target},
            ).mappings().all()
        return [_fact(row) for row in rows]

    def get_model(self, model_version: str, domain: str, target_name: str) -> dict[str, Any]:
        safe_domain, safe_target = _scope(domain, target_name)
        safe_version = str(model_version or "").strip()
        if not safe_version:
            raise ModelFactError("model_version 必须明确提供")
        if self.engine is None:
            return {}
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    f"""
                    SELECT {_MODEL_COLUMNS}
                    FROM model_registry
                    WHERE model_version = :model_version
                      AND domain = :domain AND target_name = :target_name
                    LIMIT 1
                    """
                ),
                {"model_version": safe_version, "domain": safe_domain, "target_name": safe_target},
            ).mappings().first()
        return _fact(row)

    def get_active_model(self, domain: str, target_name: str) -> dict[str, Any]:
        safe_domain, safe_target = _scope(domain, target_name)
        if self.engine is None:
            return {}
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    f"""
                    SELECT {_MODEL_COLUMNS}
                    FROM model_registry
                    WHERE domain = :domain AND target_name = :target_name
                      AND LOWER(status) = 'active' AND is_active = 1
                    ORDER BY activated_at DESC, created_at DESC
                    LIMIT 1
                    """
                ),
                {"domain": safe_domain, "target_name": safe_target},
            ).mappings().first()
        return _fact(row)

    def register_candidate(self, record: dict[str, Any]) -> dict[str, Any]:
        if self.engine is None:
            raise ModelFactError("模型事实数据库不可用")
        safe_domain, safe_target = _scope(str(record.get("domain") or ""), str(record.get("target_name") or ""))
        model_version = str(record.get("model_version") or "").strip()
        model_id = str(record.get("model_id") or "").strip()
        artifact_path = str(record.get("artifact_path") or "").strip()
        if not model_version or not model_id or not artifact_path:
            raise ModelFactError("model_id、model_version 和 artifact_path 必须明确提供")
        params = {
            "model_id": model_id,
            "model_version": model_version,
            "domain": safe_domain,
            "target_name": safe_target,
            "model_role": str(record.get("model_role") or safe_domain),
            "artifact_id": str(record.get("artifact_id") or "") or None,
            "artifact_path": artifact_path,
            "artifact_hash": str(record.get("artifact_hash") or "") or None,
            "feature_version": str(record.get("feature_version") or "") or None,
            "schema_hash": str(record.get("schema_hash") or "") or None,
            "source_type": str(record.get("source_type") or "training").strip().lower(),
            "train_start_date": record.get("train_start_date"),
            "train_end_date": record.get("train_end_date"),
            "test_mae": record.get("test_mae"),
            "test_rmse": record.get("test_rmse"),
            "peak_rmse": record.get("peak_rmse"),
            "spike_rmse": record.get("spike_rmse"),
        }
        with self.engine.begin() as conn:
            existing = conn.execute(
                text(f"SELECT {_MODEL_COLUMNS} FROM model_registry WHERE model_version = :model_version LIMIT 1"),
                {"model_version": model_version},
            ).mappings().first()
            if existing:
                current = _fact(existing)
                if current.get("domain") != safe_domain or current.get("target_name") != safe_target:
                    raise ModelFactError("同一 model_version 不得跨 domain/target 复用")
                return current
            conn.execute(
                text(
                    """
                    INSERT INTO model_registry (
                        model_id, model_version, domain, target_name, model_role,
                        artifact_id, artifact_path, artifact_hash, feature_version, schema_hash,
                        status, is_active, source_type, train_start_date, train_end_date,
                        test_mae, test_rmse, peak_rmse, spike_rmse, created_at
                    ) VALUES (
                        :model_id, :model_version, :domain, :target_name, :model_role,
                        :artifact_id, :artifact_path, :artifact_hash, :feature_version, :schema_hash,
                        'candidate', 0, :source_type, :train_start_date, :train_end_date,
                        :test_mae, :test_rmse, :peak_rmse, :spike_rmse, CURRENT_TIMESTAMP
                    )
                    """
                ),
                params,
            )
            row = conn.execute(
                text(f"SELECT {_MODEL_COLUMNS} FROM model_registry WHERE model_version = :model_version"),
                {"model_version": model_version},
            ).mappings().first()
        return _fact(row)

    def mark_validating(self, model_version: str, domain: str, target_name: str) -> dict[str, Any]:
        return self._transition(model_version, domain, target_name, {"candidate"}, "validating")

    def validate_candidate(self, model_version: str, domain: str, target_name: str) -> dict[str, Any]:
        return self._transition(
            model_version,
            domain,
            target_name,
            {"candidate", "validating"},
            "validated",
            timestamp_column="validated_at",
        )

    def reject_candidate(self, model_version: str, domain: str, target_name: str) -> dict[str, Any]:
        return self._transition(model_version, domain, target_name, {"candidate", "validating", "validated"}, "rejected")

    def activate_model(self, model_version: str, domain: str, target_name: str) -> dict[str, Any]:
        return self._activate(model_version, domain, target_name, allowed_states={"validated"})

    def rollback_active_model(self, model_version: str, domain: str, target_name: str) -> dict[str, Any]:
        return self._activate(model_version, domain, target_name, allowed_states={"archived"}, require_validated_at=True)

    def deactivate_model(self, model_version: str, domain: str, target_name: str) -> dict[str, Any]:
        return self._transition(
            model_version,
            domain,
            target_name,
            {"active"},
            "archived",
            is_active=0,
            timestamp_column="deactivated_at",
        )

    def _transition(
        self,
        model_version: str,
        domain: str,
        target_name: str,
        allowed_states: set[str],
        next_state: str,
        *,
        is_active: int = 0,
        timestamp_column: str | None = None,
    ) -> dict[str, Any]:
        safe_domain, safe_target = _scope(domain, target_name)
        safe_version = str(model_version or "").strip()
        if self.engine is None:
            raise ModelFactError("模型事实数据库不可用")
        if next_state not in MODEL_STATES:
            raise ModelFactError("不支持的模型状态")
        set_parts = ["status = :next_state", "is_active = :is_active"]
        if timestamp_column:
            set_parts.append(f"{timestamp_column} = CURRENT_TIMESTAMP")
        with self.engine.begin() as conn:
            row = self._locked_model(conn, safe_version, safe_domain, safe_target)
            if not row:
                raise ModelFactError("模型不存在或 domain/target 不匹配")
            current = _fact(row)
            if current["status"] not in allowed_states:
                raise ModelFactError(f"状态 {current['status']} 不允许转换为 {next_state}")
            conn.execute(
                text(
                    f"UPDATE model_registry SET {', '.join(set_parts)} "
                    "WHERE model_version = :model_version AND domain = :domain AND target_name = :target_name"
                ),
                {
                    "next_state": next_state,
                    "is_active": is_active,
                    "model_version": safe_version,
                    "domain": safe_domain,
                    "target_name": safe_target,
                },
            )
            updated = conn.execute(
                text(f"SELECT {_MODEL_COLUMNS} FROM model_registry WHERE model_version = :model_version"),
                {"model_version": safe_version},
            ).mappings().first()
        return _fact(updated)

    def _activate(
        self,
        model_version: str,
        domain: str,
        target_name: str,
        *,
        allowed_states: set[str],
        require_validated_at: bool = False,
    ) -> dict[str, Any]:
        safe_domain, safe_target = _scope(domain, target_name)
        safe_version = str(model_version or "").strip()
        if self.engine is None:
            raise ModelFactError("模型事实数据库不可用")
        with self.engine.begin() as conn:
            target = self._locked_model(conn, safe_version, safe_domain, safe_target)
            if not target:
                raise ModelFactError("模型不存在或 domain/target 不匹配")
            target_fact = _fact(target)
            if target_fact["status"] == "active" and target_fact["is_active"]:
                return target_fact
            if target_fact["status"] not in allowed_states:
                raise ModelFactError("只有 validated 模型或明确回滚的已验证 archived 模型可以激活")
            if require_validated_at and not target_fact.get("validated_at"):
                raise ModelFactError("未验证的 archived 模型不能回滚为 Active")
            conn.execute(
                text(
                    """
                    UPDATE model_registry
                    SET status = 'archived', is_active = 0, deactivated_at = CURRENT_TIMESTAMP
                    WHERE domain = :domain AND target_name = :target_name
                      AND LOWER(status) = 'active' AND is_active = 1
                      AND model_version <> :model_version
                    """
                ),
                {"domain": safe_domain, "target_name": safe_target, "model_version": safe_version},
            )
            result = conn.execute(
                text(
                    """
                    UPDATE model_registry
                    SET status = 'active', is_active = 1,
                        activated_at = CURRENT_TIMESTAMP, deactivated_at = NULL
                    WHERE model_version = :model_version
                      AND domain = :domain AND target_name = :target_name
                    """
                ),
                {"model_version": safe_version, "domain": safe_domain, "target_name": safe_target},
            )
            if result.rowcount != 1:
                raise ModelFactError("模型激活失败，事务已回滚")
            active = conn.execute(
                text(f"SELECT {_MODEL_COLUMNS} FROM model_registry WHERE model_version = :model_version"),
                {"model_version": safe_version},
            ).mappings().first()
        return _fact(active)

    def _locked_model(self, conn: Any, model_version: str, domain: str, target_name: str) -> Any:
        suffix = " FOR UPDATE" if conn.dialect.name == "postgresql" else ""
        return conn.execute(
            text(
                f"SELECT {_MODEL_COLUMNS} FROM model_registry "
                "WHERE model_version = :model_version AND domain = :domain AND target_name = :target_name"
                + suffix
            ),
            {"model_version": model_version, "domain": domain, "target_name": target_name},
        ).mappings().first()

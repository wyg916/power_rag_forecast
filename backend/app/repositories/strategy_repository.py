from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app.core.security import CurrentUser
from backend.app.services.strategy_governance_service import (
    StrategyGovernanceError,
    validate_reviewer,
    validate_transition,
)

from .base import dumps_json, loads_json, mapping_dict, mapping_list, postgres_engine


_JSON_FIELDS = ("evidence_json", "constraints_json", "expected_effect_json", "prohibited_actions_json")


def _engine(value: Engine | None = None) -> Engine:
    engine = value or postgres_engine()
    if engine is None:
        raise StrategyGovernanceError("strategy_database_unavailable")
    return engine


def _public(row: Any) -> dict[str, Any]:
    result = mapping_dict(row)
    for field in _JSON_FIELDS:
        result[field] = loads_json(result.get(field), default={} if field != "prohibited_actions_json" else [])
    evidence = result.get("evidence_json") if isinstance(result.get("evidence_json"), dict) else {}
    result["rule_hits"] = list(evidence.get("rule_hits") or [])
    result["explanation"] = evidence.get("explanation") or {}
    result["validation"] = evidence.get("validation") or {}
    return result


def get_strategy(strategy_id: str, *, engine: Engine | None = None) -> dict[str, Any] | None:
    with _engine(engine).connect() as conn:
        row = conn.execute(text("SELECT * FROM strategy_advice WHERE strategy_id=:strategy_id"), {"strategy_id": strategy_id}).mappings().first()
    return _public(row) if row else None


def list_strategies(
    *, run_id: str = "", report_id: str = "", status: str = "", limit: int = 100, offset: int = 0,
    engine: Engine | None = None,
) -> dict[str, Any]:
    where: list[str] = []
    params: dict[str, Any] = {"limit": max(1, min(int(limit), 500)), "offset": max(0, int(offset))}
    for field, value in (("run_id", run_id), ("report_id", report_id), ("status", status)):
        if value:
            where.append(f"{field}=:{field}")
            params[field] = value
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with _engine(engine).connect() as conn:
        total = conn.execute(text(f"SELECT count(*) FROM strategy_advice {where_sql}"), params).scalar_one()
        rows = conn.execute(
            text(f"SELECT * FROM strategy_advice {where_sql} ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"),
            params,
        ).mappings().all()
    return {"items": [_public(row) for row in rows], "total": int(total or 0), "limit": params["limit"], "offset": params["offset"]}


def list_strategy_reviews(strategy_id: str, *, engine: Engine | None = None) -> list[dict[str, Any]]:
    with _engine(engine).connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM strategy_reviews WHERE strategy_id=:strategy_id ORDER BY created_at,review_id"),
            {"strategy_id": strategy_id},
        ).mappings().all()
    result = mapping_list(rows)
    for row in result:
        row["metadata_json"] = loads_json(row.get("metadata_json"), default={})
    return result


def create_strategy(payload: dict[str, Any], *, engine: Engine | None = None) -> tuple[dict[str, Any], bool]:
    required = ("strategy_id", "run_id", "report_id", "strategy_type", "title", "summary", "content_hash")
    missing = [field for field in required if not payload.get(field)]
    if missing:
        raise StrategyGovernanceError(f"strategy_fields_missing:{','.join(missing)}")
    values = {
        **payload,
        "scenario": payload.get("scenario") or payload.get("mode") or "decision_support",
        "advice_type": payload.get("strategy_type"),
        "advice_text": payload.get("summary"),
        "status": "draft",
        "strategy_version": int(payload.get("strategy_version") or 1),
        "domain": payload.get("domain") or "strategy",
        "target_name": payload.get("target_name") or "electricity_operation",
        "evidence_json": dumps_json(payload.get("evidence_json") or {}),
        "constraints_json": dumps_json(payload.get("constraints_json") or {}),
        "expected_effect_json": dumps_json(payload.get("expected_effect_json") or {}),
        "prohibited_actions_json": dumps_json(payload.get("prohibited_actions_json") or []),
        "review_required": bool(payload.get("review_required", True)),
        "is_stale": bool(payload.get("is_stale")),
        "supersedes_strategy_id": payload.get("supersedes_strategy_id"),
    }
    sql = text(
        """
        INSERT INTO strategy_advice (
            strategy_id,strategy_version,run_id,report_id,model_version,feature_version,
            scenario,target_hour,risk_level,advice_type,advice_text,evidence_json,
            domain,target_name,strategy_type,title,summary,status,priority,confidence,
            source_type,is_stale,stale_reason,applicable_start_at,applicable_end_at,
            generated_at,created_by,rule_version,prompt_version,model_provider,model_name,
            constraints_json,expected_effect_json,prohibited_actions_json,review_required,
            supersedes_strategy_id,content_hash
        ) VALUES (
            :strategy_id,:strategy_version,:run_id,:report_id,:model_version,:feature_version,
            :scenario,:applicable_start_at,:risk_level,:advice_type,:advice_text,CAST(:evidence_json AS jsonb),
            :domain,:target_name,:strategy_type,:title,:summary,:status,:priority,:confidence,
            :source_type,:is_stale,:stale_reason,:applicable_start_at,:applicable_end_at,
            COALESCE(:generated_at,CURRENT_TIMESTAMP),:created_by,:rule_version,:prompt_version,:model_provider,:model_name,
            CAST(:constraints_json AS jsonb),CAST(:expected_effect_json AS jsonb),CAST(:prohibited_actions_json AS jsonb),:review_required,
            :supersedes_strategy_id,:content_hash
        ) ON CONFLICT (content_hash) WHERE content_hash IS NOT NULL DO NOTHING
        RETURNING *
        """
    )
    with _engine(engine).begin() as conn:
        row = conn.execute(sql, values).mappings().first()
        created = row is not None
        if created:
            conn.execute(
                text(
                    """INSERT INTO audit_logs (
                    actor,role_id,action,resource_type,resource_id,status,request_id,metadata_json
                    ) VALUES (
                    :actor,NULL,'strategy.generate','strategy',:strategy_id,'success',:request_id,CAST(:metadata_json AS jsonb)
                    )"""
                ),
                {
                    "actor": values.get("created_by"),
                    "strategy_id": values["strategy_id"],
                    "request_id": f"p5dgen:{str(values['content_hash'])[:48]}",
                    "metadata_json": dumps_json({"run_id": values["run_id"], "report_id": values["report_id"], "content_hash": values["content_hash"], "status": "draft"}),
                },
            )
        if row is None:
            row = conn.execute(text("SELECT * FROM strategy_advice WHERE content_hash=:content_hash"), {"content_hash": values["content_hash"]}).mappings().one()
    return _public(row), created


def _snapshot_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def transition_strategy(
    strategy_id: str, action: str, *, request_id: str, comment: str, user: CurrentUser,
    engine: Engine | None = None,
) -> dict[str, Any]:
    if not str(request_id or "").strip():
        raise StrategyGovernanceError("request_id_required")
    db = _engine(engine)
    with db.begin() as conn:
        existing = conn.execute(text("SELECT * FROM strategy_reviews WHERE request_id=:request_id"), {"request_id": request_id}).mappings().first()
        if existing:
            if str(existing.get("strategy_id")) != strategy_id or str(existing.get("action")) != action:
                raise StrategyGovernanceError("request_id_conflict")
            strategy = conn.execute(text("SELECT * FROM strategy_advice WHERE strategy_id=:strategy_id"), {"strategy_id": strategy_id}).mappings().one()
            return {"strategy": _public(strategy), "review": mapping_dict(existing), "idempotent": True}

        row = conn.execute(text("SELECT * FROM strategy_advice WHERE strategy_id=:strategy_id FOR UPDATE"), {"strategy_id": strategy_id}).mappings().first()
        if not row:
            raise StrategyGovernanceError("strategy_not_found")
        data = _public(row)
        decision = validate_transition(str(data.get("status")), action)
        validate_reviewer(creator=str(data.get("created_by") or ""), reviewer=user.username, reviewer_role=user.role, action=action)
        if action == "submit" and not bool((data.get("validation") or {}).get("valid")):
            raise StrategyGovernanceError("strategy_validation_failed")
        if action in {"reject", "return"} and not str(comment or "").strip():
            raise StrategyGovernanceError("review_comment_required")
        applicable_end = data.get("applicable_end_at")
        if action == "publish" and (data.get("is_stale") or str(data.get("source_type")) == "historical"):
            raise StrategyGovernanceError("stale_strategy_cannot_publish")
        if action == "publish" and applicable_end:
            end = applicable_end if isinstance(applicable_end, datetime) else datetime.fromisoformat(str(applicable_end).replace("Z", "+00:00"))
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            if end.astimezone(timezone.utc) < datetime.now(timezone.utc):
                raise StrategyGovernanceError("expired_strategy_cannot_publish")

        review_id = f"srv_{uuid.uuid4().hex}"
        evidence_hash = _snapshot_hash(data.get("evidence_json") or {})
        content_hash = str(data.get("content_hash") or "")
        conn.execute(
            text(
                """
                UPDATE strategy_advice SET status=:new_status,updated_at=CURRENT_TIMESTAMP,
                  approved_at=CASE WHEN :action='approve' THEN CURRENT_TIMESTAMP ELSE approved_at END,
                  approved_by=CASE WHEN :action='approve' THEN :actor ELSE approved_by END,
                  rejected_at=CASE WHEN :action='reject' THEN CURRENT_TIMESTAMP ELSE rejected_at END,
                  rejected_by=CASE WHEN :action='reject' THEN :actor ELSE rejected_by END,
                  rejection_reason=CASE WHEN :action='reject' THEN :comment ELSE rejection_reason END,
                  published_at=CASE WHEN :action='publish' THEN CURRENT_TIMESTAMP ELSE published_at END,
                  published_by=CASE WHEN :action='publish' THEN :actor ELSE published_by END
                WHERE strategy_id=:strategy_id
                """
            ),
            {"new_status": decision.new_status, "action": action, "actor": user.username, "comment": comment, "strategy_id": strategy_id},
        )
        review_values = {
            "review_id": review_id, "strategy_id": strategy_id, "action": action,
            "previous_status": decision.previous_status, "new_status": decision.new_status,
            "reviewer": user.username, "reviewer_role": user.role, "review_comment": comment,
            "evidence_snapshot_hash": evidence_hash, "strategy_content_hash": content_hash,
            "request_id": request_id, "metadata_json": dumps_json({"auth_mode": user.auth_mode}),
        }
        review = conn.execute(
            text(
                """INSERT INTO strategy_reviews (
                review_id,strategy_id,action,previous_status,new_status,reviewer,reviewer_role,
                review_comment,evidence_snapshot_hash,strategy_content_hash,request_id,metadata_json
                ) VALUES (
                :review_id,:strategy_id,:action,:previous_status,:new_status,:reviewer,:reviewer_role,
                :review_comment,:evidence_snapshot_hash,:strategy_content_hash,:request_id,CAST(:metadata_json AS jsonb)
                ) RETURNING *"""
            ), review_values,
        ).mappings().one()
        conn.execute(
            text(
                """INSERT INTO audit_logs (actor,role_id,action,resource_type,resource_id,status,request_id,metadata_json)
                VALUES (:actor,:role_id,:audit_action,'strategy',:strategy_id,'success',:request_id,CAST(:metadata_json AS jsonb))"""
            ),
            {"actor": user.username, "role_id": user.role, "audit_action": f"strategy.{action}", "strategy_id": strategy_id, "request_id": request_id, "metadata_json": dumps_json({"previous_status": decision.previous_status, "new_status": decision.new_status, "review_id": review_id, "content_hash": content_hash, "evidence_snapshot_hash": evidence_hash})},
        )
        updated = conn.execute(text("SELECT * FROM strategy_advice WHERE strategy_id=:strategy_id"), {"strategy_id": strategy_id}).mappings().one()
    return {"strategy": _public(updated), "review": mapping_dict(review), "idempotent": False}

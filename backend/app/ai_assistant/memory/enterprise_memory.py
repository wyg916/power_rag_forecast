from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from ...ai.identity_context import IdentityContext
from ...repositories.base import jsonable, postgres_engine


MEMORY_TYPES = {"semantic", "episodic", "procedural"}
SUBJECT_TYPES = {"user_fact", "business_fact", "system_fact", "task_episode"}
RELATION_TYPES = {"SUPPORTS", "CONTRADICTS", "SUPERSEDES", "DERIVED_FROM", "RELATED_TO"}
MEMORY_STATUSES = {"draft", "pending", "active", "cold", "archived", "deleted"}
ADMISSION_DECISIONS = {"REJECT", "SESSION_ONLY", "LONG_TERM_CANDIDATE", "LONG_TERM_ACCEPTED"}
ACCEPTED_SOURCES = {"explicit_user", "verified_business", "system_verified", "tool_verified"}
CONTEXT_BUDGET = {
    "current_session": 600,
    "semantic_memory": 800,
    "episodic_memory": 500,
    "rag_context": 1200,
    "tool_facts": 1800,
}
STATE_TRANSITIONS = {
    "draft": {"pending", "active", "archived"},
    "pending": {"active", "archived"},
    "active": {"cold", "archived"},
    "cold": {"active", "archived"},
    "archived": {"active", "deleted"},
    "deleted": set(),
}
_SENSITIVE_PATTERNS = (
    re.compile(r"(?i)(password|passwd|secret|api[_-]?key|jwt[_-]?secret|bearer)\s*[:=]"),
    re.compile(r"(?i)\bsk-[a-z0-9_-]{12,}\b"),
    re.compile(r"\b1[3-9]\d{9}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"(?:密码|密钥|令牌|身份证号|银行卡号)\s*[:：]"),
)
_EXPLICIT_MEMORY = re.compile(r"^(?:请|麻烦|帮我)?记住(?:一下)?[：:,，\s]*(?P<content>.+)$", re.DOTALL)


class MemoryCoreError(RuntimeError):
    pass


def _engine() -> Engine:
    engine = postgres_engine()
    if engine is None:
        raise MemoryCoreError("PostgreSQL enterprise memory store unavailable")
    return engine


def _identity_params(identity: IdentityContext, *, require_session: bool = False) -> dict[str, Any]:
    identity.require_valid(require_session=require_session)
    return {
        "tenant_id": identity.tenant_id,
        "workspace_id": identity.workspace_id,
        "user_id": identity.user_id,
        "agent_id": identity.agent_id,
        "session_id": identity.session_id or None,
        "run_id": identity.run_id or "latest",
    }


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def content_hash(content: str) -> str:
    normalized = re.sub(r"\s+", " ", str(content or "").strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def contains_sensitive(content: str) -> bool:
    return any(pattern.search(str(content or "")) for pattern in _SENSITIVE_PATTERNS)


def parse_explicit_memory_request(question: str) -> str:
    match = _EXPLICIT_MEMORY.match(str(question or "").strip())
    return str(match.group("content") if match else "").strip()


def is_memory_recall_question(question: str) -> bool:
    compact = re.sub(r"\s+", "", str(question or "").lower())
    return any(
        term in compact
        for term in ("还记得", "记得我", "之前记录", "我的偏好", "我的习惯", "我喜欢什么", "我不喜欢什么", "以前做过")
    )


def _score(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise MemoryCoreError(f"{name} must be numeric") from exc
    if result < 0 or result > 1:
        raise MemoryCoreError(f"{name} must be between 0 and 1")
    return result


def evaluate_admission(
    identity: IdentityContext,
    *,
    content: str,
    memory_type: str,
    source_type: str,
    confidence: float,
    importance: float,
    business_value: float,
    expires_at: datetime | None,
    duplicate_memory_id: str | None = None,
    conflict_memory_id: str | None = None,
) -> dict[str, Any]:
    identity.require_valid(require_session=False)
    reasons: list[str] = []
    value = str(content or "").strip()
    sensitive = contains_sensitive(value)
    if not value:
        reasons.append("empty_content")
    if memory_type not in MEMORY_TYPES:
        reasons.append("unsupported_memory_type")
    if source_type not in ACCEPTED_SOURCES and source_type != "session_summary":
        reasons.append("untrusted_source")
    if expires_at and expires_at <= datetime.now(timezone.utc):
        reasons.append("ttl_expired")
    if sensitive:
        reasons.append("sensitive_content")
    if duplicate_memory_id:
        reasons.append("duplicate")
    if conflict_memory_id:
        reasons.append("conflict_preserved")

    confidence = _score(confidence, "confidence")
    importance = _score(importance, "importance")
    business_value = _score(business_value, "business_value")
    if any(reason in reasons for reason in ("empty_content", "unsupported_memory_type", "untrusted_source", "ttl_expired", "sensitive_content", "duplicate")):
        decision = "REJECT"
    elif memory_type == "procedural":
        decision = "LONG_TERM_CANDIDATE"
        reasons.append("procedural_reserved_for_later_stage")
    elif source_type in ACCEPTED_SOURCES and confidence >= 0.8 and importance >= 0.6 and business_value >= 0.6:
        decision = "LONG_TERM_ACCEPTED"
        reasons.append("deterministic_long_term_gate_passed")
    elif confidence >= 0.5 and importance >= 0.4 and business_value >= 0.4:
        decision = "LONG_TERM_CANDIDATE"
        reasons.append("requires_later_review")
    else:
        decision = "SESSION_ONLY"
        reasons.append("insufficient_long_term_value")
    return {
        "decision": decision,
        "reasons": reasons,
        "contains_sensitive": sensitive,
        "confidence": confidence,
        "importance": importance,
        "business_value": business_value,
    }


def _outbox(
    connection: Connection,
    identity: IdentityContext,
    *,
    memory_id: str,
    event_type: str,
    payload: dict[str, Any],
    idempotency_key: str,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO ai_memory_outbox (
                event_id, memory_id, tenant_id, workspace_id, user_id, agent_id,
                event_type, payload, idempotency_key
            ) VALUES (
                :event_id, :memory_id, :tenant_id, :workspace_id, :user_id, :agent_id,
                :event_type, CAST(:payload AS jsonb), :idempotency_key
            ) ON CONFLICT (idempotency_key) DO NOTHING
            """
        ),
        {
            **_identity_params(identity),
            "event_id": _new_id("memevt"),
            "memory_id": memory_id,
            "event_type": event_type,
            "payload": json.dumps(jsonable(payload), ensure_ascii=False),
            "idempotency_key": idempotency_key,
        },
    )


def _state_event(
    connection: Connection,
    identity: IdentityContext,
    *,
    memory_id: str,
    from_status: str | None,
    to_status: str,
    reason: str,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO ai_memory_state_transitions (
                transition_id, memory_id, tenant_id, workspace_id, user_id, agent_id,
                from_status, to_status, reason, changed_by_run_id
            ) VALUES (
                :transition_id, :memory_id, :tenant_id, :workspace_id, :user_id, :agent_id,
                :from_status, :to_status, :reason, :run_id
            )
            """
        ),
        {
            **_identity_params(identity),
            "transition_id": _new_id("memstate"),
            "memory_id": memory_id,
            "from_status": from_status,
            "to_status": to_status,
            "reason": reason,
        },
    )


def admit_memory(
    identity: IdentityContext,
    *,
    content: str,
    summary: str = "",
    memory_type: str = "semantic",
    subject_type: str = "user_fact",
    source_type: str = "explicit_user",
    source_id: str | None = None,
    confidence: float = 0.95,
    importance: float = 0.8,
    business_value: float = 0.8,
    expires_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    params = _identity_params(identity)
    value = str(content or "").strip()
    if subject_type not in SUBJECT_TYPES:
        raise MemoryCoreError("unsupported subject_type")
    if memory_type == "episodic" and not (identity.session_id and identity.run_id and occurred_at):
        raise MemoryCoreError("episodic memory requires session_id, run_id and occurred_at")
    digest = content_hash(value)
    try:
        with _engine().begin() as connection:
            duplicate = connection.execute(
                text(
                    """
                    SELECT memory_id FROM ai_memory_records
                    WHERE tenant_id=:tenant_id AND workspace_id=:workspace_id
                      AND user_id=:user_id AND agent_id=:agent_id
                      AND content_hash=:content_hash AND status <> 'deleted'
                    ORDER BY updated_at DESC LIMIT 1
                    """
                ),
                {**params, "content_hash": digest},
            ).scalar_one_or_none()
            conflict = None
            if source_id:
                conflict = connection.execute(
                    text(
                        """
                        SELECT memory_id FROM ai_memory_records
                        WHERE tenant_id=:tenant_id AND workspace_id=:workspace_id
                          AND user_id=:user_id AND agent_id=:agent_id
                          AND source_type=:source_type AND source_id=:source_id
                          AND content_hash<>:content_hash AND status <> 'deleted'
                        ORDER BY updated_at DESC LIMIT 1
                        """
                    ),
                    {**params, "source_type": source_type, "source_id": source_id, "content_hash": digest},
                ).scalar_one_or_none()
            admission = evaluate_admission(
                identity,
                content=value,
                memory_type=memory_type,
                source_type=source_type,
                confidence=confidence,
                importance=importance,
                business_value=business_value,
                expires_at=expires_at,
                duplicate_memory_id=duplicate,
                conflict_memory_id=conflict,
            )
            admission_id = _new_id("memadm")
            connection.execute(
                text(
                    """
                    INSERT INTO ai_memory_admissions (
                        admission_id, tenant_id, workspace_id, user_id, agent_id,
                        session_id, run_id, memory_type, source_type, source_id,
                        candidate_content_hash, confidence, importance, business_value,
                        contains_sensitive, duplicate_memory_id, conflict_memory_id,
                        expires_at, decision, reasons
                    ) VALUES (
                        :admission_id, :tenant_id, :workspace_id, :user_id, :agent_id,
                        :session_id, :run_id, :memory_type, :source_type, :source_id,
                        :content_hash, :confidence, :importance, :business_value,
                        :contains_sensitive, :duplicate_memory_id, :conflict_memory_id,
                        :expires_at, :decision, CAST(:reasons AS jsonb)
                    )
                    """
                ),
                {
                    **params,
                    **admission,
                    "admission_id": admission_id,
                    "memory_type": memory_type,
                    "source_type": source_type,
                    "source_id": source_id,
                    "content_hash": digest,
                    "duplicate_memory_id": duplicate,
                    "conflict_memory_id": conflict,
                    "expires_at": expires_at,
                    "reasons": json.dumps(admission["reasons"], ensure_ascii=False),
                },
            )
            if admission["decision"] in {"REJECT", "SESSION_ONLY"}:
                return {
                    **admission,
                    "admission_id": admission_id,
                    "memory_id": duplicate,
                    "idempotent": bool(duplicate),
                }

            memory_id = _new_id("mem")
            version_id = _new_id("memv")
            status = "active" if admission["decision"] == "LONG_TERM_ACCEPTED" else "pending"
            connection.execute(
                text(
                    """
                    INSERT INTO ai_memory_records (
                        memory_id, tenant_id, workspace_id, user_id, agent_id,
                        memory_type, subject_type, content, summary, source_type, source_id,
                        confidence, importance, status, session_id, run_id, occurred_at,
                        expires_at, current_version, content_hash, metadata
                    ) VALUES (
                        :memory_id, :tenant_id, :workspace_id, :user_id, :agent_id,
                        :memory_type, :subject_type, :content, :summary, :source_type, :source_id,
                        :confidence, :importance, :status, :session_id, :run_id, :occurred_at,
                        :expires_at, 1, :content_hash, CAST(:metadata AS jsonb)
                    )
                    """
                ),
                {
                    **params,
                    "memory_id": memory_id,
                    "memory_type": memory_type,
                    "subject_type": subject_type,
                    "content": value,
                    "summary": str(summary or value)[:500],
                    "source_type": source_type,
                    "source_id": source_id,
                    "confidence": admission["confidence"],
                    "importance": admission["importance"],
                    "status": status,
                    "occurred_at": occurred_at,
                    "expires_at": expires_at,
                    "content_hash": digest,
                    "metadata": json.dumps(jsonable(metadata or {}), ensure_ascii=False),
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ai_memory_versions (
                        version_id, memory_id, version_no, content, summary, content_hash,
                        source, confidence, created_by_run_id, change_reason
                    ) VALUES (
                        :version_id, :memory_id, 1, :content, :summary, :content_hash,
                        CAST(:source AS jsonb), :confidence, :run_id, 'initial admission'
                    )
                    """
                ),
                {
                    **params,
                    "version_id": version_id,
                    "memory_id": memory_id,
                    "content": value,
                    "summary": str(summary or value)[:500],
                    "content_hash": digest,
                    "source": json.dumps({"type": source_type, "id": source_id}, ensure_ascii=False),
                    "confidence": admission["confidence"],
                },
            )
            connection.execute(
                text("UPDATE ai_memory_admissions SET memory_id=:memory_id WHERE admission_id=:admission_id"),
                {"memory_id": memory_id, "admission_id": admission_id},
            )
            _state_event(connection, identity, memory_id=memory_id, from_status=None, to_status=status, reason="admission")
            _outbox(
                connection,
                identity,
                memory_id=memory_id,
                event_type="MEMORY_CREATED",
                payload={"version_id": version_id, "version_no": 1, "memory_type": memory_type},
                idempotency_key=f"{memory_id}:1:created",
            )
            if conflict:
                _create_relation(connection, identity, memory_id, conflict, "CONTRADICTS", "admission conflict preserved")
            return {
                **admission,
                "admission_id": admission_id,
                "memory_id": memory_id,
                "version_id": version_id,
                "status": status,
                "idempotent": False,
            }
    except MemoryCoreError:
        raise
    except IntegrityError as exc:
        try:
            with _engine().connect() as connection:
                existing = connection.execute(
                    text(
                        """
                        SELECT memory_id FROM ai_memory_records
                        WHERE tenant_id=:tenant_id AND workspace_id=:workspace_id
                          AND user_id=:user_id AND agent_id=:agent_id
                          AND content_hash=:content_hash AND status <> 'deleted'
                        ORDER BY updated_at DESC LIMIT 1
                        """
                    ),
                    {**params, "content_hash": digest},
                ).scalar_one_or_none()
            if existing:
                return {
                    "decision": "REJECT",
                    "reasons": ["duplicate"],
                    "contains_sensitive": False,
                    "memory_id": existing,
                    "idempotent": True,
                }
        except Exception:
            pass
        raise MemoryCoreError("memory admission concurrency conflict") from exc
    except Exception as exc:
        raise MemoryCoreError("memory admission transaction failed") from exc


def _owned_record(connection: Connection, identity: IdentityContext, memory_id: str, *, lock: bool = False) -> dict[str, Any]:
    row = connection.execute(
        text(
            """
            SELECT * FROM ai_memory_records
            WHERE memory_id=:memory_id AND tenant_id=:tenant_id AND workspace_id=:workspace_id
              AND user_id=:user_id AND agent_id=:agent_id
            """ + (" FOR UPDATE" if lock else "")
        ),
        {**_identity_params(identity), "memory_id": memory_id},
    ).mappings().first()
    if not row:
        raise MemoryCoreError("memory not found")
    return dict(row)


def update_memory(
    identity: IdentityContext,
    memory_id: str,
    *,
    content: str,
    summary: str = "",
    confidence: float | None = None,
    change_reason: str,
) -> dict[str, Any]:
    value = str(content or "").strip()
    if not value or contains_sensitive(value) or not str(change_reason or "").strip():
        raise MemoryCoreError("memory update rejected")
    digest = content_hash(value)
    try:
        with _engine().begin() as connection:
            record = _owned_record(connection, identity, memory_id, lock=True)
            if record["content_hash"] == digest:
                return {"memory_id": memory_id, "version_no": record["current_version"], "idempotent": True}
            previous = connection.execute(
                text("SELECT version_id FROM ai_memory_versions WHERE memory_id=:memory_id AND version_no=:version_no"),
                {"memory_id": memory_id, "version_no": record["current_version"]},
            ).scalar_one()
            version_no = int(record["current_version"]) + 1
            version_id = _new_id("memv")
            score = _score(confidence if confidence is not None else record["confidence"], "confidence")
            connection.execute(
                text(
                    """
                    INSERT INTO ai_memory_versions (
                        version_id, memory_id, version_no, content, summary, content_hash,
                        source, confidence, supersedes_version_id, created_by_run_id, change_reason
                    ) VALUES (
                        :version_id, :memory_id, :version_no, :content, :summary, :content_hash,
                        CAST(:source AS jsonb), :confidence, :supersedes, :run_id, :change_reason
                    )
                    """
                ),
                {
                    **_identity_params(identity),
                    "version_id": version_id,
                    "memory_id": memory_id,
                    "version_no": version_no,
                    "content": value,
                    "summary": str(summary or value)[:500],
                    "content_hash": digest,
                    "source": json.dumps({"type": "memory_update", "previous_version": previous}),
                    "confidence": score,
                    "supersedes": previous,
                    "change_reason": change_reason,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE ai_memory_records SET content=:content, summary=:summary,
                        confidence=:confidence, current_version=:version_no,
                        content_hash=:content_hash, updated_at=CURRENT_TIMESTAMP
                    WHERE memory_id=:memory_id
                    """
                ),
                {
                    "memory_id": memory_id,
                    "content": value,
                    "summary": str(summary or value)[:500],
                    "confidence": score,
                    "version_no": version_no,
                    "content_hash": digest,
                },
            )
            _outbox(
                connection,
                identity,
                memory_id=memory_id,
                event_type="MEMORY_UPDATED",
                payload={"version_id": version_id, "version_no": version_no, "supersedes_version_id": previous},
                idempotency_key=f"{memory_id}:{version_no}:updated",
            )
            return {"memory_id": memory_id, "version_id": version_id, "version_no": version_no, "idempotent": False}
    except MemoryCoreError:
        raise
    except Exception as exc:
        raise MemoryCoreError("memory version transaction failed") from exc


def _create_relation(
    connection: Connection,
    identity: IdentityContext,
    source_memory_id: str,
    target_memory_id: str,
    relation_type: str,
    reason: str,
) -> str:
    if relation_type not in RELATION_TYPES or source_memory_id == target_memory_id:
        raise MemoryCoreError("invalid memory relation")
    _owned_record(connection, identity, source_memory_id)
    _owned_record(connection, identity, target_memory_id)
    relation_id = _new_id("memrel")
    row = connection.execute(
        text(
            """
            INSERT INTO ai_memory_relations (
                relation_id, tenant_id, workspace_id, user_id, agent_id,
                source_memory_id, target_memory_id, relation_type, reason, created_by_run_id
            ) VALUES (
                :relation_id, :tenant_id, :workspace_id, :user_id, :agent_id,
                :source_memory_id, :target_memory_id, :relation_type, :reason, :run_id
            ) ON CONFLICT (source_memory_id, target_memory_id, relation_type)
              DO UPDATE SET reason=EXCLUDED.reason
            RETURNING relation_id
            """
        ),
        {
            **_identity_params(identity),
            "relation_id": relation_id,
            "source_memory_id": source_memory_id,
            "target_memory_id": target_memory_id,
            "relation_type": relation_type,
            "reason": reason,
        },
    ).scalar_one()
    return str(row)


def create_relation(
    identity: IdentityContext,
    source_memory_id: str,
    target_memory_id: str,
    relation_type: str,
    reason: str = "",
) -> str:
    try:
        with _engine().begin() as connection:
            return _create_relation(connection, identity, source_memory_id, target_memory_id, relation_type, reason)
    except MemoryCoreError:
        raise
    except Exception as exc:
        raise MemoryCoreError("memory relation transaction failed") from exc


def transition_memory(identity: IdentityContext, memory_id: str, to_status: str, *, reason: str) -> dict[str, Any]:
    if to_status not in MEMORY_STATUSES or not reason.strip():
        raise MemoryCoreError("invalid memory transition")
    try:
        with _engine().begin() as connection:
            record = _owned_record(connection, identity, memory_id, lock=True)
            from_status = str(record["status"])
            if to_status == from_status:
                return {"memory_id": memory_id, "status": to_status, "idempotent": True}
            if to_status not in STATE_TRANSITIONS[from_status]:
                raise MemoryCoreError("memory transition not allowed")
            connection.execute(
                text("UPDATE ai_memory_records SET status=:status, updated_at=CURRENT_TIMESTAMP WHERE memory_id=:memory_id"),
                {"status": to_status, "memory_id": memory_id},
            )
            _state_event(connection, identity, memory_id=memory_id, from_status=from_status, to_status=to_status, reason=reason)
            event_type = "MEMORY_ARCHIVED" if to_status == "archived" else "MEMORY_DELETE_REQUESTED" if to_status == "deleted" else "MEMORY_UPDATED"
            _outbox(
                connection,
                identity,
                memory_id=memory_id,
                event_type=event_type,
                payload={"from_status": from_status, "to_status": to_status},
                idempotency_key=f"{memory_id}:state:{from_status}:{to_status}",
            )
            return {"memory_id": memory_id, "status": to_status, "idempotent": False}
    except MemoryCoreError:
        raise
    except Exception as exc:
        raise MemoryCoreError("memory transition transaction failed") from exc


def retrieve_memories(
    identity: IdentityContext,
    query: str,
    *,
    memory_types: Iterable[str] = ("semantic", "episodic"),
    limit: int = 5,
) -> list[dict[str, Any]]:
    types = [item for item in memory_types if item in {"semantic", "episodic"}]
    if not types:
        return []
    limit = max(1, min(int(limit), 12))
    wildcard = f"%{str(query or '').strip()[:300]}%"
    try:
        with _engine().connect() as connection:
            rows = connection.execute(
                text(
                    """
                    WITH scoped AS MATERIALIZED (
                        SELECT r.*, v.version_id
                        FROM ai_memory_records r
                        JOIN ai_memory_versions v
                          ON v.memory_id=r.memory_id AND v.version_no=r.current_version
                        WHERE r.tenant_id=:tenant_id AND r.workspace_id=:workspace_id
                          AND r.user_id=:user_id AND r.agent_id=:agent_id
                          AND r.status IN ('active', 'cold')
                          AND (r.expires_at IS NULL OR r.expires_at > CURRENT_TIMESTAMP)
                          AND r.memory_type = ANY(CAST(:memory_types AS varchar[]))
                    )
                    SELECT *,
                        (CASE WHEN content ILIKE :wildcard OR summary ILIKE :wildcard THEN 1.0 ELSE 0.0 END)
                        + importance::double precision * 0.45
                        + confidence::double precision * 0.25
                        + 0.30 / (1.0 + EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP-updated_at))/86400.0)
                        AS retrieval_score
                    FROM scoped
                    ORDER BY retrieval_score DESC, updated_at DESC
                    LIMIT :limit
                    """
                ),
                {
                    **_identity_params(identity),
                    "memory_types": types,
                    "wildcard": wildcard,
                    "limit": limit,
                },
            ).mappings().all()
        return [
            {
                "memory_id": row["memory_id"],
                "version_id": row["version_id"],
                "version_no": int(row["current_version"]),
                "memory_type": row["memory_type"],
                "subject_type": row["subject_type"],
                "content": row["content"],
                "summary": row["summary"],
                "confidence": float(row["confidence"]),
                "importance": float(row["importance"]),
                "status": row["status"],
                "occurred_at": jsonable(row["occurred_at"]),
                "updated_at": jsonable(row["updated_at"]),
                "retrieval_score": float(row["retrieval_score"]),
            }
            for row in rows
        ]
    except Exception as exc:
        raise MemoryCoreError("scoped memory retrieval failed") from exc


def build_memory_context(current_session: dict[str, Any], memories: list[dict[str, Any]]) -> dict[str, Any]:
    def clipped(items: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        used = 0
        for item in items:
            content = str(item.get("summary") or item.get("content") or "").strip()
            remaining = budget - used
            if remaining <= 0:
                break
            value = content[:remaining]
            used += len(value)
            output.append(
                {
                    "memory_id": item["memory_id"],
                    "version_id": item["version_id"],
                    "subject_type": item["subject_type"],
                    "content": value,
                    "updated_at": item.get("updated_at"),
                }
            )
        return output

    semantic = [item for item in memories if item.get("memory_type") == "semantic"]
    episodic = [item for item in memories if item.get("memory_type") == "episodic"]
    return {
        "priority_order": [
            "current_business_facts",
            "tool_verified_facts",
            "rag_authorized_evidence",
            "semantic_memory",
            "episodic_memory",
            "historical_summary",
        ],
        "budgets": CONTEXT_BUDGET,
        "current_session": jsonable(current_session),
        "semantic_memory": clipped(semantic, CONTEXT_BUDGET["semantic_memory"]),
        "episodic_memory": clipped(episodic, CONTEXT_BUDGET["episodic_memory"]),
        "memory_cannot_override_rag": True,
    }


def memory_answer(memories: list[dict[str, Any]]) -> str:
    values = [str(item.get("summary") or item.get("content") or "").strip() for item in memories]
    values = [value for value in values if value][:3]
    if not values:
        return "当前没有找到属于你且仍有效的长期记忆。"
    return "你之前明确记录过：" + "；".join(values) + "。"


def usage_items(memories: list[dict[str, Any]], *, used_in_answer: bool) -> list[dict[str, Any]]:
    return [
        {
            "memory_id": item["memory_id"],
            "version_id": item["version_id"],
            "usage_type": "answer_context",
            "retrieved_at": datetime.now(timezone.utc),
            "used_in_answer": used_in_answer,
        }
        for item in memories
    ]


def insert_memory_usages(
    connection: Connection,
    identity: IdentityContext,
    *,
    trace_id: str,
    items: list[dict[str, Any]],
) -> None:
    for item in items:
        row = connection.execute(
            text(
                """
                INSERT INTO ai_memory_usage (
                    usage_id, memory_id, version_id, tenant_id, workspace_id, user_id,
                    agent_id, session_id, run_id, trace_id, usage_type, retrieved_at, used_in_answer
                )
                SELECT CAST(:usage_id AS varchar), r.memory_id, v.version_id,
                       CAST(:tenant_id AS varchar), CAST(:workspace_id AS varchar), CAST(:user_id AS varchar),
                       CAST(:agent_id AS varchar), CAST(:session_id AS varchar), CAST(:run_id AS varchar),
                       CAST(:trace_id AS varchar), CAST(:usage_type AS varchar),
                       CAST(:retrieved_at AS timestamptz), CAST(:used_in_answer AS boolean)
                FROM ai_memory_records r
                JOIN ai_memory_versions v ON v.memory_id=r.memory_id
                WHERE r.memory_id=:memory_id AND v.version_id=:version_id
                  AND r.tenant_id=:tenant_id AND r.workspace_id=:workspace_id
                  AND r.user_id=:user_id AND r.agent_id=:agent_id
                ON CONFLICT (trace_id, memory_id, version_id, usage_type) DO NOTHING
                RETURNING usage_id
                """
            ),
            {
                **_identity_params(identity, require_session=True),
                "usage_id": _new_id("memuse"),
                "trace_id": trace_id,
                **item,
            },
        ).first()
        if row is None:
            existing = connection.execute(
                text(
                    """
                    SELECT 1 FROM ai_memory_usage
                    WHERE trace_id=:trace_id AND memory_id=:memory_id
                      AND version_id=:version_id AND usage_type=:usage_type
                    """
                ),
                {"trace_id": trace_id, **item},
            ).first()
            if not existing:
                raise MemoryCoreError("memory usage identity mismatch")

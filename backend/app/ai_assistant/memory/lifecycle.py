from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from ...ai.identity_context import IdentityContext
from . import enterprise_memory as core


ADMIN_ROLES = {"admin", "super_admin", "system_admin"}
DELETE_EVENT = "MEMORY_DELETE_REQUESTED"


def ttl_state(expires_at: datetime | None, *, now: datetime | None = None, expiring_days: int = 7) -> str:
    if expires_at is None:
        return "not_expiring"
    now = now or datetime.now(timezone.utc)
    if expires_at <= now:
        return "expired"
    return "expiring" if (expires_at - now).days < expiring_days else "not_expired"


def effective_score(
    *, importance: float, confidence: float, created_at: datetime,
    last_used_at: datetime | None, usage_count: int, memory_type: str,
    status: str = "active", now: datetime | None = None,
) -> float:
    now = now or datetime.now(timezone.utc)
    anchor = last_used_at or created_at
    age_days = max(0.0, (now - anchor).total_seconds() / 86400.0)
    recency = 0.20 / (1.0 + age_days / 30.0)
    usage = min(0.10, math.log1p(max(0, usage_count)) / 40.0)
    kind = {"semantic": 1.0, "episodic": 0.85, "procedural": 1.10}.get(memory_type, 1.0)
    temperature = 0.80 if status == "cold" else 1.0
    return round(max(0.0, min(1.0, (importance * 0.45 + confidence * 0.25 + recency + usage) * kind * temperature)), 6)


def _is_admin(identity: IdentityContext, authorized: bool) -> bool:
    return authorized and bool(set(identity.role_ids) & ADMIN_ROLES)


def _record(connection, identity: IdentityContext, memory_id: str, *, admin_authorized: bool, lock: bool = True):
    admin = _is_admin(identity, admin_authorized)
    row = connection.execute(
        text(
            "SELECT * FROM ai_memory_records WHERE memory_id=:memory_id "
            "AND tenant_id=:tenant_id AND workspace_id=:workspace_id AND agent_id=:agent_id "
            + ("" if admin else "AND user_id=:user_id ")
            + ("FOR UPDATE" if lock else "")
        ),
        {**core._identity_params(identity), "memory_id": memory_id},
    ).mappings().first()
    if not row:
        raise core.MemoryCoreError("memory not found")
    return dict(row)


def place_legal_hold(identity: IdentityContext, memory_id: str, *, reason: str, admin_authorized: bool) -> dict[str, Any]:
    if not reason.strip() or not _is_admin(identity, admin_authorized):
        raise core.MemoryCoreError("legal hold requires authorized admin")
    with core._engine().begin() as connection:
        record = _record(connection, identity, memory_id, admin_authorized=True)
        hold_id = core._new_id("memhold")
        row = connection.execute(
            text(
                "INSERT INTO ai_memory_legal_holds(hold_id,memory_id,tenant_id,workspace_id,user_id,agent_id,reason,placed_by_run_id) "
                "VALUES(:hold_id,:memory_id,:tenant_id,:workspace_id,:user_id,:agent_id,:reason,:run_id) "
                "ON CONFLICT(memory_id) WHERE active DO UPDATE SET reason=EXCLUDED.reason RETURNING hold_id"
            ),
            {**record, "hold_id": hold_id, "reason": reason, "run_id": identity.run_id},
        ).scalar_one()
        return {"hold_id": str(row), "memory_id": memory_id, "active": True}


def release_legal_hold(identity: IdentityContext, memory_id: str, *, admin_authorized: bool) -> dict[str, Any]:
    if not _is_admin(identity, admin_authorized):
        raise core.MemoryCoreError("legal hold release requires authorized admin")
    with core._engine().begin() as connection:
        _record(connection, identity, memory_id, admin_authorized=True, lock=False)
        count = connection.execute(
            text(
                "UPDATE ai_memory_legal_holds SET active=FALSE,released_at=CURRENT_TIMESTAMP,released_by_run_id=:run_id "
                "WHERE memory_id=:memory_id AND active"
            ),
            {"memory_id": memory_id, "run_id": identity.run_id},
        ).rowcount
        return {"memory_id": memory_id, "released": bool(count)}


def request_deletion(
    identity: IdentityContext, memory_id: str, *, admin_authorized: bool = False, reason: str = "user_request",
) -> dict[str, Any]:
    with core._engine().begin() as connection:
        admin = _is_admin(identity, admin_authorized)
        existing = connection.execute(
            text(
                "SELECT job_id,status FROM ai_memory_deletion_jobs WHERE idempotency_key=:key "
                "AND tenant_id=:tenant_id AND workspace_id=:workspace_id AND agent_id=:agent_id "
                + ("" if admin else "AND user_id=:user_id")
            ),
            {**core._identity_params(identity), "key": f"{memory_id}:delete"},
        ).mappings().first()
        if existing and existing["status"] == "completed":
            proof_id = connection.execute(
                text("SELECT proof_id FROM ai_memory_deletion_proofs WHERE job_id=:job_id"), existing,
            ).scalar_one_or_none()
            return {
                "job_id": str(existing["job_id"]), "memory_id": memory_id,
                "status": "completed", "proof_id": proof_id, "idempotent": True,
            }
        record = _record(connection, identity, memory_id, admin_authorized=admin_authorized)
        held = bool(connection.execute(
            text("SELECT 1 FROM ai_memory_legal_holds WHERE memory_id=:memory_id AND active"),
            {"memory_id": memory_id},
        ).first())
        job_id = str(existing["job_id"]) if existing else core._new_id("memdel")
        status = "blocked" if held else "pending"
        connection.execute(
            text(
                "INSERT INTO ai_memory_deletion_jobs(job_id,memory_id,tenant_id,workspace_id,user_id,agent_id,status,requested_by,admin_authorized,idempotency_key) "
                "VALUES(:job_id,:memory_id,:tenant_id,:workspace_id,:user_id,:agent_id,:status,:requested_by,:admin_authorized,:key) "
                "ON CONFLICT(idempotency_key) DO UPDATE SET status=EXCLUDED.status,last_error=NULL RETURNING job_id"
            ),
            {
                **record, "job_id": job_id, "status": status, "requested_by": identity.user_id,
                "admin_authorized": admin, "key": f"{memory_id}:delete",
            },
        )
        if held:
            return {"job_id": job_id, "memory_id": memory_id, "status": "blocked", "reason": "legal_hold"}
        if record["status"] != "delete_pending":
            connection.execute(
                text(
                    "UPDATE ai_memory_records SET status='delete_pending',soft_deleted_at=CURRENT_TIMESTAMP,"
                    "delete_requested_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE memory_id=:memory_id"
                ),
                {"memory_id": memory_id},
            )
            core._state_event(
                connection, identity, memory_id=memory_id, from_status=str(record["status"]),
                to_status="delete_pending", reason=reason,
            )
            core._outbox(
                connection, identity, memory_id=memory_id, event_type=DELETE_EVENT,
                payload={"job_id": job_id, "requested_by": identity.user_id},
                idempotency_key=f"{memory_id}:delete-requested",
            )
        elif existing and existing["status"] == "blocked":
            connection.execute(
                text(
                    "UPDATE ai_memory_outbox SET status='pending',available_at=CURRENT_TIMESTAMP,processed_at=NULL,last_error=NULL "
                    "WHERE idempotency_key=:key"
                ),
                {"key": f"{memory_id}:delete-requested"},
            )
        return {"job_id": job_id, "memory_id": memory_id, "status": "pending", "idempotent": bool(existing)}


def run_lifecycle_policy(identity: IdentityContext, *, now: datetime | None = None, cold_threshold: float = 0.30) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    with core._engine().connect() as connection:
        rows = [dict(row) for row in connection.execute(
            text(
                "SELECT * FROM ai_memory_records WHERE tenant_id=:tenant_id AND workspace_id=:workspace_id "
                "AND user_id=:user_id AND agent_id=:agent_id AND status IN ('active','cold','archived') ORDER BY created_at"
            ), core._identity_params(identity),
        ).mappings()]
    result = {"cold": 0, "archived": 0, "delete_requested": 0, "blocked": 0}
    for row in rows:
        expired = ttl_state(row["expires_at"], now=now) == "expired"
        if row["status"] in {"active", "cold"} and expired:
            core.transition_memory(identity, row["memory_id"], "archived", reason="ttl_expired")
            result["archived"] += 1
        elif row["status"] == "active" and effective_score(
            importance=float(row["importance"]), confidence=float(row["confidence"]),
            created_at=row["created_at"], last_used_at=row["last_used_at"], usage_count=row["usage_count"],
            memory_type=row["memory_type"], now=now,
        ) < cold_threshold:
            core.transition_memory(identity, row["memory_id"], "cold", reason="deterministic_decay")
            result["cold"] += 1
        elif row["status"] == "archived" and expired:
            requested = request_deletion(identity, row["memory_id"], reason="retention_expired")
            key = "blocked" if requested["status"] == "blocked" else "delete_requested"
            result[key] += 1
    return result


def process_outbox_batch(*, limit: int = 20, failure_injection_event_id: str = "") -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    engine = core._engine()
    with engine.connect() as probe:
        event_ids = list(probe.execute(
            text(
                "SELECT event_id FROM ai_memory_outbox WHERE event_type IN ('MEMORY_ARCHIVED','MEMORY_DELETE_REQUESTED') "
                "AND status IN ('pending','failed') AND available_at<=CURRENT_TIMESTAMP ORDER BY created_at LIMIT :limit"
            ), {"limit": max(1, min(limit, 100))},
        ).scalars())
    for event_id in event_ids:
        try:
            with engine.begin() as connection:
                event = connection.execute(
                    text("SELECT * FROM ai_memory_outbox WHERE event_id=:event_id FOR UPDATE SKIP LOCKED"),
                    {"event_id": event_id},
                ).mappings().first()
                if not event or event["status"] not in {"pending", "failed"}:
                    continue
                connection.execute(
                    text("UPDATE ai_memory_outbox SET status='processing',attempt_count=attempt_count+1 WHERE event_id=:event_id"),
                    {"event_id": event_id},
                )
                if event_id == failure_injection_event_id:
                    raise RuntimeError("controlled_failure_injection")
                if event["event_type"] == "MEMORY_ARCHIVED":
                    payload = {"archive": "retrieval_excluded", "vector": "not_applicable_current_v1", "cache": "not_applicable_no_memory_cache"}
                else:
                    job_id = str((event["payload"] or {}).get("job_id") or "")
                    held = bool(connection.execute(
                        text("SELECT 1 FROM ai_memory_legal_holds WHERE memory_id=:memory_id AND active"),
                        {"memory_id": event["memory_id"]},
                    ).first())
                    if held:
                        connection.execute(
                            text("UPDATE ai_memory_deletion_jobs SET status='blocked',last_error='legal_hold' WHERE job_id=:job_id"),
                            {"job_id": job_id},
                        )
                        payload = {"deletion": "blocked", "reason": "legal_hold"}
                    else:
                        payload = connection.execute(
                            text("SELECT ai_memory_purge(:job_id,:event_id)"),
                            {"job_id": job_id, "event_id": event_id},
                        ).scalar_one()
                connection.execute(
                    text("UPDATE ai_memory_outbox SET status='processed',processed_at=CURRENT_TIMESTAMP,last_error=NULL WHERE event_id=:event_id"),
                    {"event_id": event_id},
                )
                results.append({"event_id": event_id, "status": "processed", "result": payload})
        except Exception as exc:
            error = f"{exc.__class__.__name__}:{str(exc)[:160]}"
            with engine.begin() as connection:
                failed = connection.execute(
                    text(
                        "UPDATE ai_memory_outbox SET attempt_count=attempt_count+1,last_error=:error,"
                        "status=CASE WHEN attempt_count+1>=5 THEN 'dead_letter' ELSE 'failed' END,"
                        "available_at=CURRENT_TIMESTAMP WHERE event_id=:event_id RETURNING status,payload"
                    ), {"event_id": event_id, "error": error},
                ).mappings().first()
                job_id = str(((failed or {}).get("payload") or {}).get("job_id") or "")
                if job_id:
                    connection.execute(
                        text(
                            "UPDATE ai_memory_deletion_jobs SET attempt_count=attempt_count+1,last_error=:error,"
                            "status=CASE WHEN attempt_count+1>=max_attempts THEN 'failed' ELSE 'partial' END WHERE job_id=:job_id"
                        ), {"job_id": job_id, "error": error},
                    )
            results.append({"event_id": event_id, "status": str((failed or {}).get("status") or "failed")})
    return results

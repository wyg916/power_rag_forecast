from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.app.ai.identity_context import IdentityContext
from backend.app.ai_assistant.memory import enterprise_memory as core
from backend.app.ai_assistant.memory import lifecycle
from backend.app.db.session import get_engine


def identity(user: str = "user_a", *, tenant: str = "tenant_a", admin: bool = False) -> IdentityContext:
    return IdentityContext(
        tenant_id=tenant, workspace_id="workspace_a", user_id=user,
        role_ids=("admin",) if admin else ("analyst",), agent_id="ai_assistant",
        session_id=f"session_{user}", run_id="run_day5",
    )


def test_ttl_and_decay_are_deterministic() -> None:
    now = datetime(2026, 8, 10, tzinfo=timezone.utc)
    assert lifecycle.ttl_state(None, now=now) == "not_expiring"
    assert lifecycle.ttl_state(now - timedelta(seconds=1), now=now) == "expired"
    assert lifecycle.ttl_state(now + timedelta(days=3), now=now) == "expiring"
    recent = lifecycle.effective_score(
        importance=0.8, confidence=0.9, created_at=now - timedelta(days=5),
        last_used_at=now - timedelta(hours=1), usage_count=20, memory_type="semantic", now=now,
    )
    old = lifecycle.effective_score(
        importance=0.8, confidence=0.9, created_at=now - timedelta(days=300),
        last_used_at=None, usage_count=0, memory_type="semantic", now=now,
    )
    assert recent == lifecycle.effective_score(
        importance=0.8, confidence=0.9, created_at=now - timedelta(days=5),
        last_used_at=now - timedelta(hours=1), usage_count=20, memory_type="semantic", now=now,
    )
    assert recent > old
    assert lifecycle.effective_score(
        importance=0.8, confidence=0.9, created_at=now - timedelta(days=5),
        last_used_at=now - timedelta(hours=1), usage_count=20, memory_type="semantic", status="cold", now=now,
    ) < recent


def test_0021_contract_is_single_successor_and_security_definer_is_scoped() -> None:
    migration = Path("migrations/versions/0021_enterprise_memory_lifecycle_v1.py").read_text(encoding="utf-8")
    assert 'down_revision = "0020_enterprise_memory_core_v1"' in migration
    assert 'revision = "0021_memory_lifecycle_v1"' in migration
    for table in ("ai_memory_legal_holds", "ai_memory_deletion_jobs", "ai_memory_deletion_proofs"):
        assert f"CREATE TABLE {table}" in migration
    for status in ("pending", "running", "partial", "completed", "failed", "blocked"):
        assert status in migration
    assert "SECURITY DEFINER SET search_path FROM CURRENT" in migration
    assert "REVOKE ALL ON FUNCTION ai_memory_purge" in migration
    assert "GRANT EXECUTE ON FUNCTION ai_memory_purge" in migration
    assert "GRANT DELETE" not in migration
    assert "not_applicable_current_v1" in migration


@pytest.mark.skipif(os.environ.get("DAY5_MEMORY_LIVE_TEST") != "1", reason="isolated PostgreSQL gate only")
def test_soft_delete_retry_physical_delete_and_proof() -> None:
    owner = identity()
    with get_engine().connect() as probe:
        expected_schema = os.environ.get("DAY5_TARGET_SCHEMA") or os.environ["BETA10D_TEST_SCHEMA"]
        assert probe.execute(text("SELECT current_schema()" )).scalar_one() == expected_schema
    created = core.admit_memory(owner, content="Day5 deletion proof test", summary="deletion proof")
    related = core.admit_memory(owner, content="Day5 related record", summary="related")
    core.create_relation(owner, created["memory_id"], related["memory_id"], "RELATED_TO", "deletion relation cleanup")
    recalled = core.retrieve_memories(owner, "deletion proof")
    with core._engine().begin() as connection:
        core.insert_memory_usages(connection, owner, trace_id="day5_usage", items=core.usage_items(recalled, used_in_answer=True))

    requested = lifecycle.request_deletion(owner, created["memory_id"])
    assert requested["status"] == "pending"
    assert created["memory_id"] not in {row["memory_id"] for row in core.retrieve_memories(owner, "deletion proof")}
    with core._engine().connect() as connection:
        event_id = connection.execute(
            text("SELECT event_id FROM ai_memory_outbox WHERE memory_id=:memory_id AND event_type='MEMORY_DELETE_REQUESTED'"),
            {"memory_id": created["memory_id"]},
        ).scalar_one()
    failed = lifecycle.process_outbox_batch(failure_injection_event_id=event_id)
    assert any(item["event_id"] == event_id and item["status"] == "failed" for item in failed)
    with core._engine().connect() as connection:
        assert connection.execute(text("SELECT status FROM ai_memory_deletion_jobs WHERE job_id=:job"), {"job": requested["job_id"]}).scalar_one() == "partial"
        assert connection.execute(text("SELECT count(*) FROM ai_memory_deletion_proofs WHERE job_id=:job"), {"job": requested["job_id"]}).scalar_one() == 0

    completed = lifecycle.process_outbox_batch()
    assert any(item["event_id"] == event_id and item["status"] == "processed" for item in completed)
    with core._engine().connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM ai_memory_records WHERE memory_id=:id"), {"id": created["memory_id"]}).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM ai_memory_versions WHERE memory_id=:id"), {"id": created["memory_id"]}).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM ai_memory_relations WHERE source_memory_id=:id OR target_memory_id=:id"), {"id": created["memory_id"]}).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM ai_memory_usage WHERE memory_id=:id"), {"id": created["memory_id"]}).scalar_one() >= 1
        proof = dict(connection.execute(text("SELECT * FROM ai_memory_deletion_proofs WHERE job_id=:job"), {"job": requested["job_id"]}).mappings().one())
        assert proof["content_hash"] == core.content_hash("Day5 deletion proof test")
        assert proof["results"]["record"] == "deleted"
        assert proof["results"]["vector"] == "not_applicable_current_v1"
        assert proof["results"]["relations_deleted"] == 1
    assert lifecycle.process_outbox_batch() == []
    repeated = lifecycle.request_deletion(owner, created["memory_id"])
    assert repeated["status"] == "completed" and repeated["proof_id"] == proof["proof_id"]


@pytest.mark.skipif(os.environ.get("DAY5_MEMORY_LIVE_TEST") != "1", reason="isolated PostgreSQL gate only")
def test_legal_hold_admin_scope_archive_and_retention() -> None:
    owner = identity(user="held_user")
    admin = identity(user="admin_user", admin=True)
    foreign_admin = identity(user="admin_user", tenant="tenant_b", admin=True)
    created = core.admit_memory(owner, content="held lifecycle record", summary="held record")
    with pytest.raises(core.MemoryCoreError):
        lifecycle.place_legal_hold(owner, created["memory_id"], reason="unauthorized", admin_authorized=True)
    with pytest.raises(core.MemoryCoreError):
        lifecycle.place_legal_hold(foreign_admin, created["memory_id"], reason="cross tenant", admin_authorized=True)
    hold = lifecycle.place_legal_hold(admin, created["memory_id"], reason="audit preservation", admin_authorized=True)
    assert hold["active"] is True
    blocked = lifecycle.request_deletion(owner, created["memory_id"])
    assert blocked["status"] == "blocked"
    assert [row["memory_id"] for row in core.retrieve_memories(owner, "held record")] == [created["memory_id"]]
    assert lifecycle.release_legal_hold(admin, created["memory_id"], admin_authorized=True)["released"] is True
    requested = lifecycle.request_deletion(admin, created["memory_id"], admin_authorized=True)
    assert requested["status"] == "pending"
    assert any(row["status"] == "processed" for row in lifecycle.process_outbox_batch())

    expiring = core.admit_memory(
        owner, content="ttl lifecycle record", summary="ttl record",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    with core._engine().begin() as connection:
        connection.execute(
            text(
                "UPDATE ai_memory_records SET created_at=CURRENT_TIMESTAMP-INTERVAL '2 days',"
                "expires_at=CURRENT_TIMESTAMP-INTERVAL '1 day' WHERE memory_id=:id"
            ),
            {"id": expiring["memory_id"]},
        )
    first = lifecycle.run_lifecycle_policy(owner)
    assert first["archived"] == 1
    assert core.retrieve_memories(owner, "ttl record") == []
    assert [row["memory_id"] for row in core.retrieve_memories(owner, "ttl record", include_archived=True)] == [expiring["memory_id"]]
    second = lifecycle.run_lifecycle_policy(owner)
    assert second["delete_requested"] == 1
    lifecycle.process_outbox_batch()
    with core._engine().connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM ai_memory_records WHERE memory_id=:id"), {"id": expiring["memory_id"]}).scalar_one() == 0

    late_hold = core.admit_memory(owner, content="late legal hold", summary="late hold")
    late_request = lifecycle.request_deletion(owner, late_hold["memory_id"])
    lifecycle.place_legal_hold(admin, late_hold["memory_id"], reason="late litigation", admin_authorized=True)
    assert any(row["result"].get("deletion") == "blocked" for row in lifecycle.process_outbox_batch())
    assert lifecycle.release_legal_hold(admin, late_hold["memory_id"], admin_authorized=True)["released"] is True
    assert lifecycle.request_deletion(owner, late_hold["memory_id"])["status"] == "pending"
    lifecycle.process_outbox_batch()
    with core._engine().connect() as connection:
        assert connection.execute(text("SELECT status FROM ai_memory_deletion_jobs WHERE job_id=:job"), {"job": late_request["job_id"]}).scalar_one() == "completed"

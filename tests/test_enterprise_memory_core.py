from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.app.ai.identity_context import IdentityContext
from backend.app.ai.assistant_service import answer_chat
from backend.app.ai_assistant.memory import enterprise_memory as memory
from backend.app.core.config import get_settings
from backend.app.db.session import get_engine


def _identity(tenant: str = "tenant_a", user: str = "user_a", session: str = "session_a") -> IdentityContext:
    return IdentityContext(
        tenant_id=tenant,
        workspace_id="workspace_a",
        user_id=user,
        role_ids=("analyst",),
        agent_id="ai_assistant",
        session_id=session,
        run_id="run_day4",
    )


def test_admission_policy_is_deterministic_and_sensitive_fail_closed() -> None:
    identity = _identity()
    accepted = memory.evaluate_admission(
        identity,
        content="用户偏好简洁的经营分析摘要",
        memory_type="semantic",
        source_type="explicit_user",
        confidence=0.95,
        importance=0.8,
        business_value=0.8,
        expires_at=None,
    )
    assert accepted["decision"] == "LONG_TERM_ACCEPTED"
    assert memory.evaluate_admission(
        identity,
        content="password: should-not-store",
        memory_type="semantic",
        source_type="explicit_user",
        confidence=1,
        importance=1,
        business_value=1,
        expires_at=None,
    )["decision"] == "REJECT"
    assert memory.evaluate_admission(
        identity,
        content="一次性闲聊",
        memory_type="semantic",
        source_type="session_summary",
        confidence=0.2,
        importance=0.2,
        business_value=0.1,
        expires_at=None,
    )["decision"] == "SESSION_ONLY"
    assert memory.evaluate_admission(
        identity,
        content="预留的程序记忆",
        memory_type="procedural",
        source_type="system_verified",
        confidence=0.9,
        importance=0.9,
        business_value=0.9,
        expires_at=None,
    )["decision"] == "LONG_TERM_CANDIDATE"


def test_context_budget_and_explicit_memory_contract() -> None:
    assert memory.parse_explicit_memory_request("请记住：我偏好简洁报告") == "我偏好简洁报告"
    assert memory.parse_explicit_memory_request("普通问题") == ""
    assert memory.is_memory_recall_question("你还记得我的偏好吗？") is True
    items = [
        {
            "memory_id": "mem_1",
            "version_id": "memv_1",
            "memory_type": "semantic",
            "subject_type": "user_fact",
            "summary": "甲" * 2000,
            "content": "",
            "updated_at": "2026-08-10",
        }
    ]
    context = memory.build_memory_context({}, items)
    assert len(context["semantic_memory"][0]["content"]) == memory.CONTEXT_BUDGET["semantic_memory"]
    assert context["memory_cannot_override_rag"] is True
    assert context["priority_order"].index("rag_authorized_evidence") < context["priority_order"].index("semantic_memory")


def test_migration_declares_enterprise_memory_tables_and_downgrade() -> None:
    migration = Path("migrations/versions/0020_enterprise_memory_core_v1.py").read_text(encoding="utf-8")
    for table in memory_table_names():
        assert f"CREATE TABLE {table}" in migration
    assert "for table in reversed(MEMORY_TABLES)" in migration
    assert 'op.execute(f"DROP TABLE IF EXISTS {table}")' in migration
    for relation in memory.RELATION_TYPES:
        assert relation in migration
    for decision in memory.ADMISSION_DECISIONS:
        assert decision in migration
    assert "uq_ai_memory_scope_hash" in migration
    assert "idx_ai_memory_scope_retrieval" in migration
    assert "MEMORY_CREATED" in migration and "MEMORY_UPDATED" in migration


def memory_table_names() -> tuple[str, ...]:
    return (
        "ai_memory_records",
        "ai_memory_versions",
        "ai_memory_relations",
        "ai_memory_usage",
        "ai_memory_outbox",
        "ai_memory_admissions",
        "ai_memory_state_transitions",
    )


@pytest.mark.skipif(os.environ.get("DAY4_MEMORY_LIVE_TEST") != "1", reason="isolated PostgreSQL gate only")
def test_enterprise_memory_live_transaction_scope_and_idempotency(monkeypatch: pytest.MonkeyPatch) -> None:
    assert get_settings().has_database_url is True
    with get_engine().connect() as probe:
        assert probe.execute(text("SELECT current_schema()" )).scalar_one() == os.environ["DAY4_TARGET_SCHEMA"]
    first_session = _identity(session="session_first")
    second_session = _identity(session="session_second")
    other_user = _identity(user="user_b", session="session_other_user")
    other_tenant = _identity(tenant="tenant_b", user="user_c", session="session_other_tenant")

    created = memory.admit_memory(
        first_session,
        content="用户偏好先给结论再给依据",
        summary="偏好先结论后依据",
        source_id="preference_format",
    )
    assert created["decision"] == "LONG_TERM_ACCEPTED"
    assert created["status"] == "active"
    duplicate = memory.admit_memory(first_session, content="用户偏好先给结论再给依据")
    assert duplicate["idempotent"] is True
    assert duplicate["memory_id"] == created["memory_id"]

    recalled = memory.retrieve_memories(second_session, "我的偏好")
    assert [item["memory_id"] for item in recalled] == [created["memory_id"]]
    assert memory.retrieve_memories(other_user, "我的偏好") == []
    assert memory.retrieve_memories(other_tenant, "我的偏好") == []

    episode = memory.admit_memory(
        first_session,
        content="完成 Day4 Memory 设计评审并决定采用事务 Outbox",
        summary="Day4 设计评审采用事务 Outbox",
        memory_type="episodic",
        subject_type="task_episode",
        source_type="verified_business",
        source_id="episode_day4_design",
        occurred_at=datetime.now(timezone.utc),
    )
    assert episode["decision"] == "LONG_TERM_ACCEPTED"

    updated = memory.update_memory(
        second_session,
        created["memory_id"],
        content="用户偏好先给结论、再给依据、最后给风险",
        summary="偏好结论、依据、风险顺序",
        change_reason="用户补充了风险呈现要求",
    )
    assert updated["version_no"] == 2
    assert updated["idempotent"] is False
    assert memory.update_memory(
        second_session,
        created["memory_id"],
        content="用户偏好先给结论、再给依据、最后给风险",
        change_reason="重复请求",
    )["idempotent"] is True

    relation_id = memory.create_relation(
        second_session,
        episode["memory_id"],
        created["memory_id"],
        "RELATED_TO",
        "评审结果关联用户输出偏好",
    )
    assert relation_id.startswith("memrel_")
    conflict = memory.admit_memory(
        second_session,
        content="用户偏好先给详细背景再给结论",
        summary="相反的报告结构偏好",
        source_id="preference_format",
    )
    assert conflict["decision"] == "LONG_TERM_ACCEPTED"

    engine = memory._engine()
    with engine.connect() as connection:
        versions = connection.execute(
            text("SELECT version_no, supersedes_version_id, change_reason FROM ai_memory_versions WHERE memory_id=:id ORDER BY version_no"),
            {"id": created["memory_id"]},
        ).mappings().all()
        assert [row["version_no"] for row in versions] == [1, 2]
        assert versions[1]["supersedes_version_id"] == created["version_id"]
        assert "风险" in versions[1]["change_reason"]
        assert connection.execute(
            text("SELECT count(*) FROM ai_memory_relations WHERE relation_type='CONTRADICTS'")
        ).scalar_one() == 1

    usages = memory.usage_items(memory.retrieve_memories(second_session, "偏好"), used_in_answer=True)
    with engine.begin() as connection:
        memory.insert_memory_usages(connection, second_session, trace_id="trace_day4_usage", items=usages)
        memory.insert_memory_usages(connection, second_session, trace_id="trace_day4_usage", items=usages)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT count(*) FROM ai_memory_usage WHERE trace_id='trace_day4_usage'")
        ).scalar_one() == len(usages)
    with pytest.raises(memory.MemoryCoreError):
        with engine.begin() as connection:
            memory.insert_memory_usages(
                connection,
                other_user,
                trace_id="trace_cross_user",
                items=[usages[0]],
            )

    assert memory.transition_memory(second_session, created["memory_id"], "cold", reason="低频访问")["status"] == "cold"
    assert memory.transition_memory(second_session, created["memory_id"], "active", reason="重新使用")["status"] == "active"
    assert memory.transition_memory(second_session, created["memory_id"], "archived", reason="用户明确归档")["status"] == "archived"
    with pytest.raises(memory.MemoryCoreError):
        memory.transition_memory(second_session, created["memory_id"], "cold", reason="非法回退")

    rejected = memory.admit_memory(
        first_session,
        content="password: do-not-store-this",
        confidence=1,
        importance=1,
        business_value=1,
    )
    assert rejected["decision"] == "REJECT"
    before = _count_hash(engine, "事务失败不得留下半成品")

    def fail_outbox(*_args, **_kwargs):
        raise RuntimeError("failure injection")

    monkeypatch.setattr(memory, "_outbox", fail_outbox)
    with pytest.raises(memory.MemoryCoreError):
        memory.admit_memory(first_session, content="事务失败不得留下半成品")
    assert _count_hash(engine, "事务失败不得留下半成品") == before
    monkeypatch.undo()

    concurrent_content = "并发重复写入只保留一条长期记忆"
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(lambda _: memory.admit_memory(first_session, content=concurrent_content), range(4)))
    assert len({item["memory_id"] for item in outcomes}) == 1
    assert sum(not item["idempotent"] for item in outcomes) == 1
    assert _count_hash(engine, concurrent_content) == 1

    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM ai_memory_outbox")).scalar_one() >= 8
        assert connection.execute(text("SELECT count(*) FROM ai_memory_admissions")).scalar_one() >= 6
        assert connection.execute(text("SELECT count(*) FROM ai_memory_state_transitions")).scalar_one() >= 7


def _count_hash(engine, content: str) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text("SELECT count(*) FROM ai_memory_records WHERE content_hash=:hash"),
                {"hash": memory.content_hash(content)},
            ).scalar_one()
        )


@pytest.mark.skipif(os.environ.get("DAY4_MEMORY_LIVE_TEST") != "1", reason="isolated PostgreSQL gate only")
def test_ai_assistant_explicit_write_cross_session_recall_and_usage() -> None:
    base = _identity(session="unused")
    written = answer_chat(
        "请记住：我偏好三句话以内的经营摘要",
        session_id="assistant_memory_write",
        run_id="run_assistant_write",
        identity=base,
    )
    assert written["memory"]["admission"] == "LONG_TERM_ACCEPTED"
    assert "后续会话" in written["answer"]

    recalled = answer_chat(
        "你还记得我的偏好吗？",
        session_id="assistant_memory_recall",
        run_id="run_assistant_recall",
        identity=base,
    )
    assert "三句话以内" in recalled["answer"]
    assert recalled["memory"]["used_in_answer"] is True
    assert recalled["memory"]["retrieved_count"] >= 1

    foreign = answer_chat(
        "你还记得我的偏好吗？",
        session_id="assistant_memory_foreign",
        run_id="run_assistant_foreign",
        identity=_identity(user="user_foreign", session="unused"),
    )
    assert "三句话以内" not in foreign["answer"]
    assert foreign["memory"]["retrieved_count"] == 0

    with memory._engine().connect() as connection:
        usage = connection.execute(
            text(
                """
                SELECT count(*) AS total, bool_and(used_in_answer) AS all_used
                FROM ai_memory_usage WHERE trace_id=:trace_id
                """
            ),
            {"trace_id": recalled["trace_id"]},
        ).mappings().one()
        assert usage["total"] >= 1
        assert usage["all_used"] is True

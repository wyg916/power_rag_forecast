from __future__ import annotations

from types import SimpleNamespace

from backend.app.ai.identity_context import IdentityContext
from backend.app.ai_assistant import service
from backend.app.ai_assistant.context_pack_builder import build_context_pack
from backend.app.ai_assistant.schemas import IntentDecision
from scripts.rag_r1_candidate_ai_acceptance import _digit_issues


def _identity(tenant: str, user: str) -> IdentityContext:
    return IdentityContext(
        tenant_id=tenant,
        workspace_id="workspace",
        user_id=user,
        role_ids=("viewer",),
    )


def _retrieval_context(tenant: str, user: str) -> SimpleNamespace:
    return SimpleNamespace(tenant_id=tenant, user_id=user, roles=("viewer",))


def test_composite_answer_stops_before_tools_when_authorized_context_is_empty(monkeypatch):
    tool_called = False

    def tools(*args, **kwargs):
        nonlocal tool_called
        tool_called = True
        return []

    monkeypatch.setattr(service, "_execute_tools", tools)
    monkeypatch.setattr(service, "get_conversation_state", lambda identity: None)
    monkeypatch.setattr(
        service,
        "rag_search",
        lambda *args, **kwargs: {"available": False, "items": [], "citations": [], "retrieval": {}},
    )

    payload = service.answer_chat_accurate(
        "最新成功预测的最高电价是多少，并说明高价风险边界？",
        identity=_identity("other-tenant", "user-a"),
        rag_context=_retrieval_context("other-tenant", "user-a"),
        enterprise_store=object(),
        debug=True,
        persist=False,
    )

    assert payload["unavailable_reason"] == "authorized_context_unavailable"
    assert payload["tool_calls"] == []
    assert payload["evidence"] == []
    assert tool_called is False


def test_retrieval_identity_mismatch_fails_closed_before_search(monkeypatch):
    monkeypatch.setattr(service, "get_conversation_state", lambda identity: None)
    monkeypatch.setattr(service, "rag_search", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not search")))

    payload = service.answer_chat_accurate(
        "依据知识库，实时事实不可用时应如何回答？",
        identity=_identity("tenant-a", "user-a"),
        rag_context=_retrieval_context("tenant-b", "user-a"),
        enterprise_store=object(),
        debug=True,
        persist=False,
    )

    assert payload["unavailable_reason"] == "identity_scope_mismatch"
    assert payload["citations"] == []


def test_context_pack_declares_fixed_authorization_order():
    identity = _identity("tenant-a", "user-a").with_session("session-a")
    pack = build_context_pack(
        question="问题",
        decision=IntentDecision("knowledge_search", 1.0, {}, "问题"),
        results=[],
        evidence=[],
        run_id="latest",
        identity=identity,
        memory_context={"last_topic": "历史话题"},
    )

    assert pack["context_order"] == [
        "SYSTEM_POLICY", "IDENTITY_SCOPE", "QUESTION", "AUTHORIZED_CONTEXT",
        "TOOL_FACTS", "MEMORY_CONTEXT", "ANSWER_CONSTRAINTS",
        "CITATION_REQUIREMENTS", "OUTPUT_SCHEMA",
    ]
    assert pack["identity_scope"]["tenant_id"] == "tenant-a"
    assert pack["system_policy"]["current_authorized_facts_override_memory"] is True


def test_source_state_contract_uses_canonical_status_terms():
    answer = service._enforce_source_state_terms("历史或过期文档如何处理？", "不作为当前事实。")
    unavailable = service._enforce_source_state_terms("实时事实不可用时如何回答？", "说明数据缺口。")
    closed = service._enforce_source_state_terms("schema hash 不一致怎么办？", "停止处理。")

    assert "historical" in answer
    assert "unavailable" in unavailable
    assert "fail-closed" in closed


def test_domain_rules_prioritize_primary_business_semantics():
    assert service._rag_domain_hint("如果预测数据不足，AI 助手应该如何说明？") == "data_quality"
    assert service._rag_domain_hint("高价时段应该怎么做风险应对？") == "trading_strategy"
    assert service._rag_domain_hint("显式 run_id 对应的最低电价是多少？") == "price_forecast"
    assert service._rag_domain_hint("特征缺列或 schema hash 不一致怎么办？") == "price_forecast"
    assert service._rag_domain_hint("日前电价预测值能不能直接作为交易价格？") == "trading_strategy"
    assert service._rag_domain_hint("DOM 节点电价分析应该如何解释？") == "electricity_market"
    assert service._rag_domain_hint("新能源出力变化怎么影响价格？") == "renewable_policy"
    assert service._rag_domain_hint("负荷预测偏低会带来什么交易风险？") == "trading_strategy"


def test_verified_business_tool_output_supports_answer_digits():
    result = {
        "question": "最新价格是多少？",
        "answer": "最新价格为 64.21。",
        "citations": [],
        "evidence": [],
        "tool_fact_errors": [],
        "verified_tool_facts": [
            {"tool_name": "get_forecast_metrics", "output": {"avg_price": 64.21}}
        ],
    }

    assert _digit_issues(result) == []


def test_verified_business_tool_output_supports_display_rounding_only():
    result = {
        "question": "最新价格是多少？",
        "answer": "最新价格为 64.21，未经验证的价格为 88.88。",
        "citations": [],
        "evidence": [],
        "tool_fact_errors": [],
        "verified_tool_facts": [
            {"tool_name": "get_forecast_metrics", "output": {"avg_price": 64.2149}}
        ],
    }

    assert _digit_issues(result) == ["88.88"]


def test_risk_hour_answer_uses_bullets_without_synthetic_row_numbers():
    decision = IntentDecision("forecast_risk_hours", 1.0, {}, "高价风险小时")
    result = SimpleNamespace(
        name="get_high_risk_hours",
        output={"items": [{"hour": "18:00", "risk_level": "高", "predicted_price": 64.2149}]},
    )

    answer = service._build_answer(decision, [result])

    assert "1. 18:00" not in answer
    assert "- 18:00" in answer

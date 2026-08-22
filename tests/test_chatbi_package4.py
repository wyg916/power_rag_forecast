from __future__ import annotations

import json
import os

import pytest

from backend.app.ai.identity_context import IdentityContext
from backend.app.chatbi.contracts import AnalysisPlan
from backend.app.chatbi.memory import (
    CHATBI_CONTEXT_KEYS,
    analysis_context,
    apply_remembered_context,
    recall_analysis_context,
)
from backend.app.chatbi.planner import AnalysisPlanGenerationError, generate_analysis_plan, parse_analysis_plan
from backend.app.chatbi.service import execute_chatbi_turn
from backend.app.chatbi.validator import validate_analysis_plan
from backend.app.db.session import get_engine


def full_plan(**overrides) -> AnalysisPlan:
    payload = {
        "datasets": ["market_price_history"],
        "metrics": ["avg_day_ahead_price"],
        "dimensions": ["market_observed_at", "market_code"],
        "filters": [{"dimension": "market_code", "operator": "eq", "value": "DOM"}],
        "time_range": {"start": "2020-01-01T00:00:00", "end": "2020-01-01T23:00:00"},
        "group_by": ["market_code"],
        "order_by": [{"field": "avg_day_ahead_price", "direction": "desc"}],
        "limit": 10,
        "chart_intent": "bar",
    }
    payload.update(overrides)
    return AnalysisPlan.model_validate(payload)


def identity(user: str = "user_a", session: str = "session_a", run: str = "run_a") -> IdentityContext:
    return IdentityContext(
        tenant_id="tenant_a",
        workspace_id="workspace_a",
        user_id=user,
        role_ids=("analyst",),
        agent_id="chatbi",
        session_id=session,
        run_id=run,
    )


class FakePlanLLM:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.messages: list[dict[str, str]] = []

    def generate_answer(self, messages, **_kwargs):
        self.messages = messages
        return json.dumps(self.payload, ensure_ascii=False), {"provider": "test_llm", "model": "frozen", "fallback": False}


class FlakyPlanLLM(FakePlanLLM):
    def __init__(self, payload: dict) -> None:
        super().__init__(payload)
        self.calls = 0

    def generate_answer(self, messages, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return "not-json", {"provider": "test_llm", "model": "frozen", "fallback": False}
        return super().generate_answer(messages, **kwargs)


def test_memory_snapshot_contains_only_approved_chatbi_context() -> None:
    payload = analysis_context(full_plan(comparison="yoy", drill_level=None))
    assert tuple(payload) == CHATBI_CONTEXT_KEYS
    assert payload["metric"] == ["avg_day_ahead_price"]
    assert "datasets" not in payload and "joins" not in payload and "sql" not in payload


def test_omitted_fields_restore_but_explicit_current_query_wins() -> None:
    remembered = analysis_context(full_plan(comparison="yoy"))
    current = AnalysisPlan.model_validate({"comparison": "mom", "filters": []})
    resolved, meta = apply_remembered_context(current, remembered)
    assert resolved.metrics == ["avg_day_ahead_price"]
    assert resolved.filters == []
    assert resolved.comparison == "mom"
    assert resolved.datasets == ["market_price_history"] and resolved.group_by == ["market_code"]
    assert meta["used"] and set(meta["restored_fields"]) >= {"metric", "dimensions", "time_range"}
    assert validate_analysis_plan(resolved, permissions=("data:read",)).valid


def test_explicit_empty_dimensions_are_not_repopulated_from_memory() -> None:
    remembered = analysis_context(full_plan())
    current = AnalysisPlan.model_validate({"metrics": ["avg_actual_load"], "dimensions": [], "filters": []})
    resolved, _ = apply_remembered_context(current, remembered)
    assert resolved.metrics == ["avg_actual_load"] and resolved.dimensions == []
    assert resolved.datasets == ["load_history"] and resolved.group_by == []


def test_fresh_llm_plan_derives_only_registered_dataset_and_grouping() -> None:
    draft = AnalysisPlan.model_validate({
        "metrics": ["avg_actual_load"],
        "dimensions": ["load_observed_at", "load_market_code"],
    })
    resolved, meta = apply_remembered_context(draft, None)
    assert resolved.datasets == ["load_history"]
    assert resolved.group_by == ["load_market_code"]
    assert resolved.chart_intent == "bar" and not meta["used"]


def test_llm_generates_only_analysis_plan_and_omitted_fields_remain_omitted() -> None:
    router = FakePlanLLM({"comparison": "mom"})
    plan, metadata = generate_analysis_plan("那环比呢", analysis_context(full_plan()), router=router)
    assert plan.comparison == "mom" and "metrics" not in plan.model_fields_set
    assert metadata["source"] == "llm_analysis_plan" and metadata["provider"] == "test_llm"
    assert "只输出一个 JSON 对象" in router.messages[0]["content"]


@pytest.mark.parametrize("raw", [
    '{"datasets":["market_price_history"],"metrics":["avg_day_ahead_price"],"sql":"DROP TABLE users"}',
    "SELECT * FROM users",
    '{"metrics":["invented_metric"],"rogue_field":true}',
])
def test_plan_parser_rejects_sql_and_unknown_contract_fields(raw: str) -> None:
    with pytest.raises(AnalysisPlanGenerationError):
        parse_analysis_plan(raw)


def test_plan_parser_applies_one_safe_json_normalization_for_provider_variants() -> None:
    plan = parse_analysis_plan("""```json
    {"analysis_plan": {
      "dataset_id": "market_price_history",
      "metric": "avg_day_ahead_price",
      "dimension": "market_code",
      "filters": null,
      "groupBy": null,
      "orderBy": null,
      "joins": null,
      "chartIntent": "TABLE",
      "analysisMode": "AGGREGATE",
      "clarificationRequired": false
    }}
    ```""")
    assert plan.datasets == ["market_price_history"]
    assert plan.metrics == ["avg_day_ahead_price"]
    assert plan.dimensions == ["market_code"]
    assert plan.filters == [] and plan.group_by == [] and plan.order_by == [] and plan.joins == []
    assert plan.chart_intent == "table" and plan.analysis_mode == "aggregate"


def test_recall_filters_wrong_session_and_non_chatbi_memory(monkeypatch) -> None:
    expected = analysis_context(full_plan())
    items = [
        {"source_type": "tool_verified", "source_id": "chatbi_context:other:plan_x", "session_id": "other", "content": json.dumps(expected)},
        {"source_type": "explicit_user", "source_id": "preference", "session_id": "session_a", "content": json.dumps(expected)},
        {"source_type": "tool_verified", "source_id": "chatbi_context:session_a:plan_ok", "session_id": "session_a", "content": json.dumps(expected)},
    ]
    observed = {}

    def fake_retrieve(*_args, **kwargs):
        observed.update(kwargs)
        return items

    monkeypatch.setattr("backend.app.chatbi.memory.retrieve_memories", fake_retrieve)
    assert recall_analysis_context(identity()) == expected
    assert observed["session_id"] == "session_a" and observed["memory_types"] == ("episodic",)


def test_generated_invalid_plan_becomes_audited_business_clarification(monkeypatch) -> None:
    observed: dict[str, AnalysisPlan] = {}
    router = FakePlanLLM(
        {
            "datasets": ["market_price_history"],
            "metrics": ["invented_metric"],
            "chart_intent": "table",
        }
    )

    monkeypatch.setattr("backend.app.chatbi.service.recall_analysis_context", lambda *_args, **_kwargs: None)

    def fake_execute(**kwargs):
        observed["plan"] = kwargs["plan"]
        return {
            "state": "clarification_required",
            "analysis_plan": kwargs["plan"].model_dump(mode="json"),
        }

    monkeypatch.setattr("backend.app.chatbi.service.execute_chatbi_analysis", fake_execute)
    response = execute_chatbi_turn(
        question="分析一下经营情况",
        plan=None,
        identity=identity(),
        permissions=("assistant:use", "data:read", "model:read"),
        engine=object(),
        planner_router=router,
    )

    assert response["state"] == "clarification_required"
    assert observed["plan"].clarification_required
    assert "业务指标" in observed["plan"].clarification_question
    assert response["planner"]["generated_plan_state"] == "clarification_required"
    assert "unregistered_metric" in response["planner"]["validation_issue_codes"]


def test_auto_plan_generation_retries_one_contract_failure(monkeypatch) -> None:
    router = FlakyPlanLLM(
        {
            "clarification_required": True,
            "clarification_question": "请说明要分析的指标和时间范围。",
        }
    )
    monkeypatch.setattr("backend.app.chatbi.service.recall_analysis_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "backend.app.chatbi.service.execute_chatbi_analysis",
        lambda **kwargs: {
            "state": "clarification_required",
            "analysis_plan": kwargs["plan"].model_dump(mode="json"),
        },
    )

    response = execute_chatbi_turn(
        question="分析一下经营情况",
        plan=None,
        identity=identity(),
        permissions=("assistant:use", "data:read", "model:read"),
        engine=object(),
        planner_router=router,
    )

    assert router.calls == 2
    assert response["state"] == "clarification_required"
    assert response["planner"]["attempts"] == 2


@pytest.mark.skipif(
    os.environ.get("BETA10D_TEST_DATABASE_MODE") != "isolated-schema",
    reason="isolated PostgreSQL gate only",
)
def test_multi_turn_uses_enterprise_memory_and_prevents_cross_scope_recall() -> None:
    engine = get_engine()
    first = execute_chatbi_turn(
        question="按市场看平均日前电价",
        plan=full_plan(),
        identity=identity(),
        permissions=("assistant:use", "data:read", "model:read"),
        engine=engine,
    )
    assert first["memory_context"]["persisted"] and not first["memory_context"]["used"]

    follow_up = execute_chatbi_turn(
        question="那环比呢",
        plan=AnalysisPlan.model_validate({"comparison": "mom"}),
        identity=identity(run="run_b"),
        permissions=("assistant:use", "data:read", "model:read"),
        engine=engine,
    )
    assert follow_up["memory_context"]["used"] and follow_up["memory_context"]["persisted"]
    assert follow_up["memory_context"]["parent_analysis_plan_id"] == first["lineage"]["analysis_plan_id"]
    assert follow_up["analysis_plan"]["metrics"] == ["avg_day_ahead_price"]
    assert follow_up["analysis_plan"]["comparison"] == "mom"
    assert recall_analysis_context(identity(user="user_b", run="run_other"), engine=engine) is None
    assert recall_analysis_context(identity(session="session_other", run="run_other"), engine=engine) is None

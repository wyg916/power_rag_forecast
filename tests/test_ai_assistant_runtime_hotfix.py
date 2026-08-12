from __future__ import annotations

import json

from backend.app.ai_assistant.runtime_router import AssistantRoute, route_assistant_request, route_requires_rag
from backend.app.ai_assistant.core.intent_router import route_intent
from backend.app.ai_assistant.service import _should_use_rag
from backend.app.ai_assistant.templates.fallback_answers import answer_high_price_reason
from backend.app.chatbi.planner import generate_analysis_plan, parse_analysis_plan, repair_analysis_plan
from backend.app.services.rag_qdrant_transport import _preproduction_candidate_is_accepted


def test_required_questions_are_routed_before_enterprise_runtime() -> None:
    assert route_assistant_request("今天几号？") == AssistantRoute.GENERAL_CHAT
    assert route_assistant_request("数据库最新的天气数据是哪天？") == AssistantRoute.CHATBI
    assert route_assistant_request("对比历史同期情况") == AssistantRoute.RAG_QA
    assert route_assistant_request("解释高价风险原因") == AssistantRoute.BUSINESS_ANALYSIS


def test_business_tool_routes_do_not_open_rag_as_a_hard_prerequisite() -> None:
    assert route_requires_rag(AssistantRoute.BUSINESS_ANALYSIS) is False
    assert route_requires_rag(AssistantRoute.BUSINESS_ADVICE) is False
    assert route_requires_rag(AssistantRoute.REPORT_GENERATION) is False
    assert route_requires_rag(AssistantRoute.RAG_QA) is True
    assert _should_use_rag("high_price_reason", "complex_analysis", "解释高价风险原因") is False
    assert _should_use_rag("report_summary", "complex_analysis", "生成完整分析报告") is False
    assert _should_use_rag("knowledge_search", "complex_analysis", "对比历史同期情况") is True


def test_purchase_advice_and_policy_questions_use_business_routes() -> None:
    assert route_intent("建议购电策略").intent == "trading_risk_summary"
    assert route_assistant_request(
        "建议购电策略", answer_style="business_advice"
    ) == AssistantRoute.BUSINESS_ADVICE
    assert route_intent("政策解读与影响").intent == "tariff_policy_search"
    assert route_assistant_request("政策解读与影响") == AssistantRoute.RAG_QA


def test_plan_parser_normalizes_provider_wrappers_and_camel_case() -> None:
    plan = parse_analysis_plan({
        "message": {
            "reasoning_content": "internal reasoning is ignored",
            "content": "```json\n" + json.dumps({
                "analysisPlan": {
                    "dataSets": ["weather_history"],
                    "metrics": ["avg_temperature"],
                    "timeRange": {
                        "start": "2026-08-01T00:00:00",
                        "end": "2026-08-12T23:59:59",
                    },
                    "chartIntent": "line",
                }
            }) + "\n```",
        }
    })
    assert plan.datasets == ["weather_history"]
    assert plan.metrics == ["avg_temperature"]
    assert plan.chart_intent == "line"


class _RepairingPlanner:
    def __init__(self) -> None:
        self.calls = 0

    def generate_answer(self, messages, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return "not-json", {"provider": "deepseek", "model": "test"}
        assert '"repair":true' in messages[-1]["content"]
        return json.dumps({"metrics": ["avg_temperature"]}), {
            "provider": "deepseek", "model": "test", "finish_reason": "stop"
        }


def test_planner_performs_one_targeted_repair() -> None:
    router = _RepairingPlanner()
    plan, metadata = generate_analysis_plan("数据库最新天气是哪天？", None, router=router)
    assert router.calls == 2
    assert plan.metrics == ["avg_temperature"]
    assert metadata["repair_attempted"] is True
    assert metadata["finish_reason"] == "stop"


def test_planner_reserves_reasoning_budget_for_structured_output() -> None:
    class BudgetRouter:
        def __init__(self) -> None:
            self.max_tokens: list[int] = []

        def generate_answer(self, messages, **kwargs):
            self.max_tokens.append(kwargs["max_tokens"])
            return '{"datasets":[],"metrics":[],"dimensions":[],"filters":[],"group_by":[],"order_by":[],"limit":100,"joins":[],"chart_intent":"table","analysis_mode":"aggregate","clarification_required":true,"clarification_question":"请补充指标"}', {"provider": "deepseek", "model": "deepseek-v4-flash"}

    router = BudgetRouter()
    plan, _ = generate_analysis_plan("分析数据", {}, requested_provider="deepseek", router=router)
    assert plan.clarification_required is True
    assert router.max_tokens == [6000]


def test_deterministic_validation_repair_is_single_call() -> None:
    class RepairRouter:
        def __init__(self) -> None:
            self.calls = 0

        def generate_answer(self, messages, **kwargs):
            self.calls += 1
            assert '"metric_required"' in messages[-1]["content"]
            return json.dumps({
                "datasets": ["weather_observations"],
                "metrics": ["avg_temperature"],
                "dimensions": ["weather_observed_at"],
                "order_by": [{"field": "weather_observed_at", "direction": "desc"}],
                "limit": 1,
                "chart_intent": "table",
                "analysis_mode": "aggregate",
            }), {"provider": "deepseek", "model": "deepseek-v4-flash", "finish_reason": "stop"}

    invalid = parse_analysis_plan(json.dumps({
        "datasets": ["weather_observations"],
        "metrics": [],
        "dimensions": ["weather_observed_at"],
    }))
    router = RepairRouter()
    plan, metadata = repair_analysis_plan(
        "数据库最新的天气数据是哪天？",
        {},
        invalid,
        [{"code": "metric_required", "field": "metrics", "message": "指标必填"}],
        requested_provider="deepseek",
        router=router,
    )
    assert router.calls == 1
    assert plan.metrics == ["avg_temperature"]
    assert metadata["repair_attempted"] is True


def test_latest_weather_plan_is_normalized_to_registered_contract() -> None:
    class LatestWeatherRouter:
        def generate_answer(self, messages, **kwargs):
            return json.dumps({
                "datasets": ["weather_observations"],
                "metrics": [],
                "dimensions": ["weather_observed_at"],
                "order_by": [{"field": "weather_observed_at", "direction": "desc"}],
                "limit": 1,
                "chart_intent": "table",
                "analysis_mode": "ranking",
            }), {"provider": "deepseek", "model": "deepseek-v4-flash", "finish_reason": "stop"}

    plan, metadata = generate_analysis_plan(
        "数据库最新的天气数据是哪天？", {}, requested_provider="deepseek", router=LatestWeatherRouter()
    )
    assert plan.metrics == ["avg_temperature"]
    assert plan.group_by == ["weather_observed_at"]
    assert plan.analysis_mode == "aggregate"
    assert metadata["latest_fact_normalized"] is True


def test_high_price_empty_fact_is_explicit_and_contains_no_none() -> None:
    answer = answer_high_price_reason({})
    assert "暂不能判断" in answer
    assert "None" not in answer


def test_frozen_rag_r1_candidate_evidence_is_accepted_without_alias_switch() -> None:
    assert _preproduction_candidate_is_accepted("RAG-R1", "rag_chunks_RAG-R1")

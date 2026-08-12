from __future__ import annotations

import json

from backend.app.ai_assistant.runtime_router import AssistantRoute, route_assistant_request
from backend.app.ai_assistant.templates.fallback_answers import answer_high_price_reason
from backend.app.chatbi.planner import generate_analysis_plan, parse_analysis_plan
from backend.app.services.rag_qdrant_transport import _preproduction_candidate_is_accepted


def test_required_questions_are_routed_before_enterprise_runtime() -> None:
    assert route_assistant_request("今天几号？") == AssistantRoute.GENERAL_CHAT
    assert route_assistant_request("数据库最新的天气数据是哪天？") == AssistantRoute.CHATBI
    assert route_assistant_request("对比历史同期情况") == AssistantRoute.RAG_QA
    assert route_assistant_request("解释高价风险原因") == AssistantRoute.BUSINESS_ANALYSIS


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


def test_high_price_empty_fact_is_explicit_and_contains_no_none() -> None:
    answer = answer_high_price_reason({})
    assert "暂不能判断" in answer
    assert "None" not in answer


def test_frozen_rag_r1_candidate_evidence_is_accepted_without_alias_switch() -> None:
    assert _preproduction_candidate_is_accepted("RAG-R1", "rag_chunks_RAG-R1")

from __future__ import annotations

import pytest

from backend.app.ai_assistant.core.intent_router import route_intent
from backend.app.ai_assistant.service import answer_chat_accurate
from backend.app.services import rag_service
from backend.app.ai_assistant.tools.tariff_tools import DATA_DIR, check_station_tariff, query_market_power_price, query_southern_grid_tax_rule, search_tariff_policy
from backend.app.ai_assistant.tools.knowledge_tools import search_business_knowledge


requires_tariff_assets = pytest.mark.skipif(
    not (DATA_DIR / "pv_station_tariff_check.csv").is_file(),
    reason="requires Git-external tariff assets; set TARIFF_ASSET_ROOT",
)


def test_tariff_intents_are_routed_to_tools():
    assert route_intent("查询浙江衢州2017年并网光伏补贴电价").intent == "tariff_query"
    assert route_intent("206120201604419 这个电站电价核对是否有差异").intent == "station_tariff_check"
    assert route_intent("广东潮州饶平南网税率和回款公式").intent == "southern_grid_tax_query"


@requires_tariff_assets
def test_station_tariff_check_uses_tariff_asset():
    result = check_station_tariff(question="请核对电站编码 206120201604419 的电价")
    assert result["available"] is True
    assert result["station_id"] == "206120201604419"
    assert result["city"] == "衢州市"


@requires_tariff_assets
def test_policy_and_knowledge_search_return_evidence(monkeypatch):
    policy = search_tariff_policy(question="光伏补贴政策 发改文件")
    assert policy["available"] is True
    assert policy["items"]
    monkeypatch.setattr(
        rag_service,
        "rag_search",
        lambda query, top_k=5, domain="": {
            "items": [{"chunk_id": "chunk-test", "doc_id": "doc-test", "title": "policy", "content": query, "final_score": 0.9}],
            "citations": [{"chunk_id": "chunk-test", "doc_id": "doc-test"}],
            "source_type": "postgresql",
        },
    )
    knowledge = search_business_knowledge(question="光伏补贴政策")
    assert knowledge["available"] is True
    assert knowledge["items"]


@requires_tariff_assets
def test_market_and_tax_tools_return_rules():
    market = query_market_power_price(question="山东省2025年1月市电综合电价")
    assert market["available"] is True
    assert market["total_price"] is not None
    tax = query_southern_grid_tax_rule(question="广东潮州饶平南网税率")
    assert tax["available"] is True
    assert tax["deduction_rate"] is not None


def test_ai_assistant_station_answer_calls_tool():
    data = answer_chat_accurate("帮我核对电站编码 206120201604419 的电价", session_id="test_tariff_tool", debug=True)
    assert data["intent"] == "station_tariff_check"
    assert data["tools"][0]["name"] == "check_station_tariff"
    assert "电站" in data["answer"]

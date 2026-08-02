from __future__ import annotations

from backend.app.ai_assistant.core.intent_router import route_intent
from backend.app.ai_assistant.service import answer_chat_accurate
from backend.app.ai_assistant.tools.tariff_tools import check_station_tariff, query_market_power_price, query_southern_grid_tax_rule, search_tariff_policy
from backend.app.ai_assistant.tools.knowledge_tools import search_business_knowledge


def test_tariff_intents_are_routed_to_tools():
    assert route_intent("查询浙江衢州2017年并网光伏补贴电价").intent == "tariff_query"
    assert route_intent("206120201604419 这个电站电价核对是否有差异").intent == "station_tariff_check"
    assert route_intent("广东潮州饶平南网税率和回款公式").intent == "southern_grid_tax_query"


def test_station_tariff_check_uses_tariff_asset():
    result = check_station_tariff(question="请核对电站编码 206120201604419 的电价")
    assert result["available"] is True
    assert result["station_id"] == "206120201604419"
    assert result["city"] == "衢州市"


def test_policy_search_uses_asset_but_knowledge_file_fallback_stays_disabled():
    policy = search_tariff_policy(question="光伏补贴政策 发改文件")
    assert policy["available"] is True
    assert policy["items"]
    knowledge = search_business_knowledge(question="光伏补贴政策")
    assert knowledge["available"] is False
    assert knowledge["items"] == []
    assert knowledge["citations"] == []


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

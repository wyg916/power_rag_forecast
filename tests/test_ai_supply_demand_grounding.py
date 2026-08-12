from __future__ import annotations

from backend.app.ai_assistant.core.intent_router import route_intent
from backend.app.ai_assistant.service import _rag_trigger_decision


def test_supply_demand_question_requires_business_grounding() -> None:
    decision = route_intent("当前电力供需如何？请给出结论和依据。")

    assert decision.intent == "trading_risk_summary"
    use_rag, trigger = _rag_trigger_decision(
        decision.intent,
        "complex_analysis",
        decision.normalized_question,
    )
    assert use_rag is True
    assert "供需" in trigger["matched_terms"]

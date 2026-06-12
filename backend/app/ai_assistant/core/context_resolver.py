from __future__ import annotations

from ..schemas import ConversationState, IntentDecision
from .input_normalizer import compact_question


def resolve_followup(question: str, state: ConversationState | None) -> IntentDecision | None:
    if not state:
        return None
    q = compact_question(question)
    reason_words = {"为什么", "为啥", "什么原因", "原因呢"}
    detail_words = {"具体说说", "详细说说", "展开说说"}
    action_words = {"那怎么处理", "怎么处理", "怎么办", "怎么做"}
    if q in reason_words:
        if state.last_topic == "low_price_window":
            return IntentDecision("low_price_reason", 0.96, {"target_time": state.last_focus_time}, question)
        if state.last_topic == "high_price_window":
            return IntentDecision("high_price_reason", 0.96, {"target_time": state.last_focus_time}, question)
        if state.last_topic == "high_risk_hour":
            return IntentDecision("risk_reason", 0.96, {"target_time": state.last_focus_time}, question)
        if state.last_topic == "storage_discharge":
            return IntentDecision("storage_spread_analysis", 0.92, {"target_time": state.last_focus_time}, question)
    if q in detail_words and state.last_intent:
        return IntentDecision(state.last_intent, 0.9, {"target_time": state.last_focus_time}, question)
    if q in action_words and state.last_topic in {"high_risk_hour", "high_price_window", "anomaly"}:
        return IntentDecision("trading_exposure_advice", 0.92, {"target_time": state.last_focus_time}, question)
    return None

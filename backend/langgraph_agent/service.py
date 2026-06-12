from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.app.ai.answer_guard import validate_answer
from backend.app.data_access import jsonable

from .graph import PowerAgentGraph
from .schemas import PROFESSIONAL_INTENTS
from .state import AgentState


def should_use_agent(question: str, intent: str | None = None) -> bool:
    text = (question or "").strip()
    if not text:
        return False
    if intent in PROFESSIONAL_INTENTS or intent == "weather_analysis":
        return True
    professional_keywords = ["电价", "负荷", "新能源", "售电", "交易", "预测", "日报", "风险", "模型", "储能"]
    if any(key in text for key in professional_keywords):
        return True
    # Dify 未启用时，通用兜底也走 Agent，避免旧固定模板答非所问。
    return True


def analyze_question(
    question: str,
    session_id: str | None = None,
    run_id: str = "latest",
    market: str | None = None,
    date: str | None = None,
    page_context: dict[str, Any] | None = None,
    scenario: str = "power_trading",
    user_role: str = "trader",
    answer_style: str = "analysis",
    trace_id: str | None = None,
) -> dict[str, Any]:
    state = AgentState(
        question=(question or "").strip(),
        session_id=session_id,
        run_id=run_id,
        market=market,
        date=date,
        page_context=page_context,
        scenario=scenario,
        user_role=user_role,
        answer_style=answer_style,
    )
    if trace_id:
        state.trace_id = trace_id
    state = PowerAgentGraph().run(state)
    answer, evidence = validate_answer(state.intent, state.answer, state.evidence)
    state.answer = answer
    state.evidence = evidence
    return jsonable(
        {
            "session_id": session_id,
            "answer": state.answer,
            "intent": state.intent,
            "entities": state.entities,
            "confidence": state.confidence,
            "complexity": state.complexity,
            "engine": state.engine,
            "workflow": state.workflow,
            "agent_trace": state.agent_trace,
            "evidence": state.evidence,
            "tool_calls": state.tool_calls,
            "related_actions": state.related_actions,
            "risk_level": state.risk_level,
            "focus_periods": state.focus_periods,
            "data_used": state.data_used,
            "suggestions": state.suggestions[:6],
            "model_used": state.model_used,
            "model_error": state.model_error,
            "trace_id": state.trace_id,
            "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        }
    )

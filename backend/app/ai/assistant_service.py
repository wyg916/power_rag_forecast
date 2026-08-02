from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from ..data_access import jsonable
from .answer_guard import validate_answer
from .chat_memory import save_chat_exchange
from .context_builder import build_answer
from .dify_client import DifyClient
from .intent_classifier import classify
from .tool_registry import call_tools
from backend.langgraph_agent.service import analyze_question, should_use_agent
from backend.app.ai_assistant.service import answer_chat_accurate


def _data_used(tool_calls: list[dict[str, Any]]) -> dict[str, bool]:
    names = {str(call.get("tool_name") or "") for call in tool_calls if call.get("success")}
    return {
        "prediction": bool(names & {"get_prediction_overview", "get_forecast_extremes", "get_high_risk_hours", "get_trading_advice"}),
        "weather": "get_weather_forecast" in names,
        "load": "get_load_forecast" in names,
        "renewable": "get_renewable_forecast" in names,
        "history": "get_market_history" in names,
        "knowledge": "search_knowledge" in names,
        "model": bool(names & {"get_model_error_summary", "get_model_explain"}),
        "report": "get_report_summary" in names,
    }


def _risk_level(tool_results: list[dict[str, Any]]) -> str:
    for item in tool_results:
        if item.get("risk_level"):
            return str(item.get("risk_level"))
        if item.get("tool") == "get_prediction_overview" and item.get("overview", {}).get("risk_level"):
            return str(item["overview"]["risk_level"])
    return ""


def _suggestions(tool_results: list[dict[str, Any]], related_actions: list[dict[str, Any]]) -> list[str]:
    output: list[str] = []
    for item in tool_results:
        overview = item.get("overview") if isinstance(item.get("overview"), dict) else item
        for value in overview.get("focus_periods") or []:
            output.append(f"重点关注 {value} 时段")
        for value in overview.get("main_factors") or []:
            output.append(str(value))
    output.extend(str(action.get("label")) for action in related_actions if action.get("label"))
    seen: set[str] = set()
    deduped: list[str] = []
    for item in output:
        if item and item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped[:6]


def answer_chat(
    question: str,
    session_id: str | None = None,
    run_id: str = "latest",
    market: str | None = None,
    date: str | None = None,
    page_context: dict[str, Any] | None = None,
    scenario: str = "power_trading",
    user_role: str = "trader",
    answer_style: str = "analysis",
    model_provider: str = "auto",
    debug: bool = False,
    retrieval_context: Any = None,
    enterprise_store: Any = None,
    enterprise_unavailable_reason: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    clean_question = (question or "").strip()
    return answer_chat_accurate(
        clean_question,
        session_id=session_id,
        run_id=run_id,
        market=market,
        date=date,
        page_context=page_context,
        scenario=scenario,
        user_role=user_role,
        answer_style=answer_style,
        model_provider=model_provider,
        debug=debug,
        retrieval_context=retrieval_context,
        enterprise_store=enterprise_store,
        enterprise_unavailable_reason=enterprise_unavailable_reason,
        trace_id=trace_id,
    )

    session_id = session_id or "chat_" + uuid.uuid4().hex[:12]
    trace_id = "trace_" + uuid.uuid4().hex[:12]
    intent_result = classify(clean_question)
    if market and not intent_result.entities.get("market"):
        intent_result.entities["market"] = market
    if date and not intent_result.entities.get("date"):
        intent_result.entities["date"] = date
    if page_context:
        intent_result.entities["page_context"] = page_context

    if should_use_agent(clean_question, intent_result.intent):
        agent_payload = analyze_question(
            clean_question,
            session_id=session_id,
            run_id=run_id,
            market=market,
            date=date,
            page_context=page_context,
            scenario=scenario,
            user_role=user_role,
            answer_style=answer_style,
            trace_id=trace_id,
        )
        agent_payload["session_id"] = session_id
        save_chat_exchange(
            session_id=session_id,
            question=clean_question,
            answer=str(agent_payload.get("answer") or ""),
            intent=str(agent_payload.get("intent") or intent_result.intent),
            evidence=agent_payload.get("evidence") or [],
            tool_calls=agent_payload.get("tool_calls") or [],
            user_role=user_role,
            scenario=scenario,
            trace_id=trace_id,
        )
        return jsonable(agent_payload)

    dify_payload: dict[str, Any] | None = None
    try:
        dify = DifyClient()
        if dify.enabled():
            dify_payload = dify.chat(
                clean_question,
                session_id=session_id,
                inputs={
                    "market": intent_result.entities.get("market"),
                    "date": intent_result.entities.get("date"),
                    "page_context": page_context or {},
                    "run_id": run_id,
                    "scenario": scenario,
                    "user_role": user_role,
                },
            )
    except Exception:
        dify_payload = None

    if dify_payload and dify_payload.get("answer"):
        answer = str(dify_payload["answer"])
        evidence: list[dict[str, Any]] = [{"name": "Dify 应用回答", "value": "已调用", "source": "dify"}]
        save_chat_exchange(
            session_id=dify_payload.get("session_id") or session_id,
            question=clean_question,
            answer=answer,
            intent=intent_result.intent,
            evidence=evidence,
            tool_calls=[],
            user_role=user_role,
            scenario=scenario,
            trace_id=trace_id,
        )
        return jsonable(
            {
                "session_id": dify_payload.get("session_id") or session_id,
                "answer": answer,
                "intent": intent_result.intent,
                "entities": intent_result.entities,
                "confidence": intent_result.confidence,
                "evidence": evidence,
                "tool_calls": [],
                "related_actions": [],
                "risk_level": "",
                "data_used": {"dify": True},
                "suggestions": [],
                "trace_id": trace_id,
                "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
            }
        )

    tool_results, tool_calls = call_tools(intent_result.intent, intent_result.entities, run_id=run_id, question=clean_question)
    draft = build_answer(
        clean_question,
        intent_result.intent,
        intent_result.entities,
        tool_results,
        user_role=user_role,
        scenario=scenario,
        answer_style=answer_style,
    )
    answer, evidence = validate_answer(intent_result.intent, draft["answer"], draft.get("evidence") or [])
    related_actions = draft.get("related_actions") or []

    save_chat_exchange(
        session_id=session_id,
        question=clean_question,
        answer=answer,
        intent=intent_result.intent,
        evidence=evidence,
        tool_calls=tool_calls,
        user_role=user_role,
        scenario=scenario,
        trace_id=trace_id,
    )

    return jsonable(
        {
            "session_id": session_id,
            "answer": answer,
            "intent": intent_result.intent,
            "entities": intent_result.entities,
            "confidence": intent_result.confidence,
            "evidence": evidence,
            "tool_calls": tool_calls,
            "related_actions": related_actions,
            "risk_level": _risk_level(tool_results),
            "data_used": _data_used(tool_calls),
            "suggestions": _suggestions(tool_results, related_actions),
            "trace_id": trace_id,
            "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        }
    )

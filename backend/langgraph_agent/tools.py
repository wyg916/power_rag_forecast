from __future__ import annotations

from typing import Any

from backend.app.ai.tool_registry import TOOLS

from .schemas import TOOL_DATA_SOURCE
from .state import AgentState


def _tool_input(state: AgentState, name: str) -> dict[str, Any]:
    args: dict[str, Any] = {
        "run_id": state.run_id,
        "market": state.entities.get("market") or state.market,
        "date": state.entities.get("date") or state.date,
        "question": state.question,
    }
    if name == "get_hour_detail":
        args["hour"] = state.entities.get("hour")
    if name == "get_weather_forecast":
        city = state.entities.get("city")
        if city:
            args["city"] = city
    return args


def run_agent_tools(state: AgentState) -> AgentState:
    for name in state.required_tools:
        try:
            if name == "build_hour_risk_evidence":
                args = {"hour_detail": state.tool_results[-1] if state.tool_results else {}}
            else:
                args = _tool_input(state, name)
            result = TOOLS[name](**args)
            success = not bool(result.get("empty"))
            state.tool_results.append(result)
            state.tool_calls.append({"tool_name": name, "input": args, "success": success, "output": result})
            source = TOOL_DATA_SOURCE.get(name)
            if source and success:
                state.data_used[source] = True
        except Exception as exc:
            result = {"tool": name, "empty": True, "message": str(exc)}
            state.tool_results.append(result)
            state.tool_calls.append({"tool_name": name, "input": _tool_input(state, name), "success": False, "error_message": str(exc), "output": result})
    return state

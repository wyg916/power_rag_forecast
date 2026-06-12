from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    question: str
    session_id: str | None = None
    run_id: str = "latest"
    market: str | None = None
    date: str | None = None
    page_context: dict[str, Any] | None = None
    scenario: str = "power_trading"
    user_role: str = "trader"
    answer_style: str = "analysis"
    trace_id: str = field(default_factory=lambda: "trace_" + uuid.uuid4().hex[:12])
    engine: str = "local_graph_fallback"
    intent: str = "general_analysis"
    confidence: float = 0.0
    entities: dict[str, Any] = field(default_factory=dict)
    complexity: str = "simple"
    professional: bool = False
    required_tools: list[str] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    workflow: list[str] = field(default_factory=list)
    agent_trace: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
    risk_level: str = ""
    focus_periods: list[str] = field(default_factory=list)
    data_used: dict[str, bool] = field(default_factory=dict)
    related_actions: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    model_used: bool = False
    model_error: str = ""

    def trace(self, agent: str, status: str, summary: str = "", **extra: Any) -> None:
        self.workflow.append(agent)
        item = {"agent": agent, "status": status}
        if summary:
            item["summary"] = summary
        item.update(extra)
        self.agent_trace.append(item)

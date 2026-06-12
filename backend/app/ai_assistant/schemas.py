from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntentDecision:
    intent: str
    confidence: float
    entities: dict[str, Any] = field(default_factory=dict)
    normalized_question: str = ""


@dataclass
class ConversationState:
    session_id: str
    last_intent: str = ""
    last_topic: str = ""
    last_focus_time: str = ""
    last_focus_metric: str = ""
    last_focus_value: str = ""
    last_run_id: str = "latest"
    last_answer_summary: str = ""


@dataclass
class ToolResult:
    name: str
    input: dict[str, Any]
    output: dict[str, Any]
    success: bool = True
    error_message: str = ""


@dataclass
class AnswerPlan:
    answer_mode: str
    use_llm: bool
    template: str = ""

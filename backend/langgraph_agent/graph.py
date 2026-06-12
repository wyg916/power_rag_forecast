from __future__ import annotations

from .nodes import answer_agent, data_agent, intent_agent, prediction_agent, report_agent, risk_agent
from .state import AgentState

try:
    import langgraph  # type: ignore  # noqa: F401

    LANGGRAPH_AVAILABLE = True
except Exception:
    LANGGRAPH_AVAILABLE = False


class PowerAgentGraph:
    """第二阶段多 Agent 工作流。

    当前项目不强制依赖外部 langgraph 包；如果运行环境已安装 langgraph，
    返回会标记 engine=langgraph_ready，否则使用同构的本地顺序图执行器。
    """

    def __init__(self) -> None:
        self.engine = "langgraph_ready" if LANGGRAPH_AVAILABLE else "local_graph_fallback"
        self.nodes = [intent_agent, data_agent, prediction_agent, risk_agent, report_agent, answer_agent]

    def run(self, state: AgentState) -> AgentState:
        state.engine = self.engine
        for node in self.nodes:
            state = node(state)
        return state

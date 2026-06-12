from __future__ import annotations

import importlib
from typing import Callable


LogFunc = Callable[[str], None] | None


def build_ai_summary(log: LogFunc = None) -> None:
    if log:
        log("通过 report_service 构造 AI 输入摘要。")
    importlib.import_module("02_build_ai_summary").main()


def generate_llm_report(log: LogFunc = None) -> None:
    if log:
        log("通过 report_service 生成 LLM 报告。")
    importlib.import_module("03_llm_generate_report").main()

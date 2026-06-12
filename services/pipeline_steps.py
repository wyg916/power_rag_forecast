from __future__ import annotations

import importlib
import os
from contextlib import contextmanager
from typing import Any, Callable, Mapping

from automation_common import get_run_context

from .data_service import refresh_market_data
from .dispatch_service import dispatch_report
from .prediction_service import run_prediction
from .report_service import build_ai_summary, generate_llm_report


LogFunc = Callable[[str], None] | None


@contextmanager
def _patched_environ(env: Mapping[str, str] | None):
    if not env:
        yield
        return
    old_values = {key: os.environ.get(key) for key in env}
    os.environ.update({str(k): str(v) for k, v in env.items()})
    try:
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def run_pipeline_step(
    script_name: str,
    config: dict[str, Any],
    env: Mapping[str, str] | None = None,
    log: LogFunc = None,
) -> None:
    """统一调度入口：main_daily_run 通过服务层触发各阶段。"""

    with _patched_environ(env):
        if script_name == "00_local_model_inventory.py":
            importlib.import_module("00_local_model_inventory").main()
        elif script_name == "fetch_power_market_data.py":
            refresh_market_data(config=config, log=log)
        elif script_name == "01_run_prediction.py":
            run_prediction(config=config, run_context=get_run_context(), log=log, env=env)
        elif script_name == "02_build_ai_summary.py":
            build_ai_summary(log=log)
        elif script_name == "03_llm_generate_report.py":
            generate_llm_report(log=log)
        elif script_name == "04_dispatch_report.py":
            dispatch_report(log=log)
        else:
            raise ValueError(f"未注册的流水线服务步骤：{script_name}")

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from automation_common import get_pipeline_paths, load_config
from database_utils import test_database_connection


def load_runtime_config(config_path: str | Path | None = None) -> dict[str, Any]:
    return load_config(Path(config_path) if config_path else None)


def get_runtime_paths(config: dict[str, Any] | None = None):
    return get_pipeline_paths(config or load_runtime_config())


def build_pipeline_env(run_id: str, run_mode: str, run_started_at: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PIPELINE_RUN_ID"] = run_id
    env["PIPELINE_RUN_MODE"] = run_mode
    env["PIPELINE_RUN_STARTED_AT"] = run_started_at
    return env


def disable_database_if_unavailable(config: dict[str, Any], log=None) -> bool:
    ok, message = test_database_connection(config)
    if log:
        log(message)
    if not ok:
        config.setdefault("database", {})["enabled"] = False
        os.environ["DB_ENABLED"] = "0"
        if log:
            log("数据库不可用，已切换为本地文件模式。")
    return ok

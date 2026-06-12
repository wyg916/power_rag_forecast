from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping

from .legacy_engine import DEFAULT_ENGINE_SCRIPT, load_engine_module


def run_prediction_engine(
    engine_script: str | Path | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """以兼容脚本方式运行预测引擎，保证输出与原主流程一致。"""

    script = Path(engine_script) if engine_script else DEFAULT_ENGINE_SCRIPT
    root = Path(cwd) if cwd else script.parent
    merged_env = os.environ.copy()
    if env:
        merged_env.update({str(k): str(v) for k, v in env.items()})
    merged_env["PYTHONUTF8"] = "1"
    return subprocess.run([sys.executable, str(script)], cwd=str(root), check=False, env=merged_env)


def run_training_pipeline() -> None:
    """进程内运行 v4_fix1 main，主要用于后续服务化入口。"""

    load_engine_module().main()

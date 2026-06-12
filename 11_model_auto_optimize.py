from __future__ import annotations

import os

from automation_common import get_pipeline_paths, get_run_context, load_config, setup_run_logger
from services.config_service import disable_database_if_unavailable
from services.operations_service import run_model_auto_optimize


def main() -> None:
    config = load_config()
    paths = get_pipeline_paths(config)
    log, _ = setup_run_logger(paths.log_dir, "11_model_auto_optimize")
    disable_database_if_unavailable(config, log=log)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    result = run_model_auto_optimize(config, run_context=get_run_context(), env=env, log=log)
    log(f"模型自动优化结果：{result}")


if __name__ == "__main__":
    main()

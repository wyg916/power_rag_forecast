from __future__ import annotations

from automation_common import get_pipeline_paths, load_config, setup_run_logger
from services.config_service import disable_database_if_unavailable
from services.operations_service import run_model_ops_daily


def main() -> None:
    config = load_config()
    paths = get_pipeline_paths(config)
    log, _ = setup_run_logger(paths.log_dir, "06_model_monitor")
    disable_database_if_unavailable(config, log=log)
    result = run_model_ops_daily(config, log=log)
    log(f"模型运维检查结果：{result}")


if __name__ == "__main__":
    main()

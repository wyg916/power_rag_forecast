from __future__ import annotations

from automation_common import get_pipeline_paths, load_config, setup_run_logger
from model_ops.actuals_updater import update_actuals_and_errors
from services.config_service import disable_database_if_unavailable


def main() -> None:
    config = load_config()
    paths = get_pipeline_paths(config)
    log, _ = setup_run_logger(paths.log_dir, "05_update_actuals_and_errors")
    disable_database_if_unavailable(config, log=log)
    result = update_actuals_and_errors(config, log=log)
    log(f"真实值回填结果：{result}")


if __name__ == "__main__":
    main()

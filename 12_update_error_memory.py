from __future__ import annotations

from automation_common import get_pipeline_paths, load_config, setup_run_logger
from model_ops.actuals_updater import update_actuals_and_errors
from model_ops.error_memory import summarize_error_memory, update_error_memory
from services.config_service import disable_database_if_unavailable


def main() -> None:
    config = load_config()
    paths = get_pipeline_paths(config)
    log, _ = setup_run_logger(paths.log_dir, "12_update_error_memory")
    db_ok = disable_database_if_unavailable(config, log=log)
    if not db_ok:
        log("数据库不可用，无法更新误差记忆。")
        return
    actual_result = update_actuals_and_errors(config, log=log)
    log(f"真实值回填结果：{actual_result}")
    rows = update_error_memory(config, log=log)
    summary = summarize_error_memory(config)
    log(f"误差记忆更新完成：写入 {rows} 个分层场景，总样本数 {summary.get('sample_count', 0)}。")


if __name__ == "__main__":
    main()

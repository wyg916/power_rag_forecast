from __future__ import annotations

from automation_common import get_pipeline_paths, load_config, now_compact, now_text
from database_utils import (
    apply_database_migrations,
    ensure_database_structures,
    sync_core_datasets_to_database,
    sync_result_tables_to_database,
    test_database_connection,
)
from model_ops.prediction_tracker import build_prediction_tracking_frame, load_future_result_excel, write_prediction_tracking


def log(message: str) -> None:
    print(message)


def sync_prediction_tracking_from_latest_result(config: dict, run_id: str) -> int:
    paths = get_pipeline_paths(config)
    future_path = paths.result_table_dir / "18_未来24小时预测结果_正式版.xlsx"
    if not future_path.exists():
        log(f"未找到正式前瞻预测结果，跳过 prediction_tracking 补齐：{future_path}")
        return 0

    future_result = load_future_result_excel(future_path)
    tracking_df = build_prediction_tracking_frame(
        future_result,
        run_id=run_id,
        model_version="legacy_latest_result",
        feature_version="result_table_sync",
    )
    return write_prediction_tracking(config, tracking_df, run_id=run_id, log=log)


def main() -> int:
    config = load_config()
    paths = get_pipeline_paths(config)
    ok, message = test_database_connection(config)
    log(message)
    if not ok:
        return 2

    run_id = f"manual_db_closure_{now_compact()}"
    context = {
        "run_id": run_id,
        "run_mode": "database_closure",
        "run_started_at": now_text(),
    }
    apply_database_migrations(config, log=log)
    sync_core_datasets_to_database(paths.data_dir, config, log=log)
    sync_result_tables_to_database(paths.result_table_dir, config, run_context=context, log=log)
    tracked_rows = sync_prediction_tracking_from_latest_result(config, run_id)
    ensure_database_structures(config, log=log)
    log(f"数据库闭环同步完成：run_id={run_id}，prediction_tracking={tracked_rows} 条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

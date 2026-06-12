from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pandas as pd

from automation_common import get_pipeline_paths, load_config
from database_utils import sync_core_datasets_to_database


LogFunc = Callable[[str], None] | None


def _log(log: LogFunc, message: str) -> None:
    if log:
        log(message)


def _repair_forecast_load_selected(data_dir: Path, log: LogFunc = None) -> None:
    selected_path = data_dir / "forecast_load_selected.xlsx"
    if selected_path.exists() and selected_path.stat().st_size > 0:
        return

    raw_path = data_dir / "forecast_load_raw.xlsx"
    if not raw_path.exists() or raw_path.stat().st_size <= 0:
        _log(log, "WARNING: 未发现可用的 forecast_load_raw.xlsx，无法自动修复 forecast_load_selected.xlsx。")
        return

    try:
        import fetch_power_market_data

        forecast_df = pd.read_excel(raw_path, engine="openpyxl")
        selected_df = fetch_power_market_data.choose_day_ahead_forecast(forecast_df)
        if selected_df.empty:
            _log(log, "WARNING: forecast_load_raw.xlsx 未筛选出可用日前负荷预测记录，保留现有预测输入。")
            return
        fetch_power_market_data.write_dataset(selected_path, selected_df)
        _log(log, f"SUCCESS: 已从 forecast_load_raw.xlsx 自动修复 forecast_load_selected.xlsx，记录数：{len(selected_df)}。")
    except Exception as exc:
        _log(log, f"WARNING: 自动修复 forecast_load_selected.xlsx 失败，后续将复用数据库或既有文件：{exc}")


def _fallback_to_local_market_data(config: dict[str, Any], log: LogFunc = None) -> None:
    paths = get_pipeline_paths(config)
    _log(log, "WARNING: PJM 外部数据刷新未完成，复用本地/数据库现有数据继续流程。")
    _repair_forecast_load_selected(paths.data_dir, log=log)
    try:
        sync_core_datasets_to_database(paths.data_dir, config, log=log)
    except Exception as exc:
        _log(log, f"WARNING: 本地核心数据同步数据库失败，主流程将继续使用现有数据：{exc}")


def refresh_market_data(config: dict[str, Any] | None = None, log: LogFunc = None) -> None:
    """刷新外部市场数据；失败时降级复用本地数据。"""

    runtime_config = config or load_config()
    _log(log, "通过 data_service 调用数据刷新流程。")

    try:
        import fetch_power_market_data

        fetch_power_market_data.main()
    except Exception as exc:
        _log(log, f"WARNING: PJM 外部数据刷新失败，降级复用本地/数据库现有数据继续流程：{exc}")
        _fallback_to_local_market_data(runtime_config, log=log)

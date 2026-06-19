from __future__ import annotations

import sys

from backend.app.config import PROJECT_ROOT


def command_for_kind(kind: str) -> list[str]:
    py = sys.executable
    mapping = {
        "today_analysis": [py, "-X", "utf8", str(PROJECT_ROOT / "main_daily_run.py"), "--refresh-data", "--fast-forecast"],
        "refresh_data": [py, "-X", "utf8", str(PROJECT_ROOT / "fetch_power_market_data.py")],
        "sync_core_data": [py, "-X", "utf8", str(PROJECT_ROOT / "13_sync_core_data_to_db.py")],
        "fast_forecast": [py, "-X", "utf8", str(PROJECT_ROOT / "main_daily_run.py"), "--fast-forecast"],
        "report_only": [py, "-X", "utf8", str(PROJECT_ROOT / "main_daily_run.py"), "--skip-prediction"],
        "health_check": [py, "-X", "utf8", str(PROJECT_ROOT / "09_health_check.py")],
        "retrain_model": [py, "-X", "utf8", str(PROJECT_ROOT / "main_daily_run.py"), "--retrain-model"],
        "model_auto_optimize": [py, "-X", "utf8", str(PROJECT_ROOT / "main_daily_run.py"), "--model-auto-optimize"],
        "forecast_run": [py, "-X", "utf8", str(PROJECT_ROOT / "main_daily_run.py"), "--fast-forecast"],
        "data_sync": [py, "-X", "utf8", str(PROJECT_ROOT / "13_sync_core_data_to_db.py")],
    }
    if kind not in mapping:
        raise ValueError(f"Unsupported task kind: {kind}")
    return mapping[kind]

from __future__ import annotations

from datetime import datetime
from typing import Any

from ...data_access import data_status, load_latest_forecast


def get_current_date_context(**_: Any) -> dict[str, Any]:
    now = datetime.now()
    weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
    forecast = load_latest_forecast()
    summary = forecast.get("summary") or {}
    sources = data_status().get("sources") or []
    latest_times = [str(item.get("latest_time")) for item in sources if item.get("latest_time")]
    return {
        "tool": "get_current_date_context",
        "available": True,
        "system_date": now.date().isoformat(),
        "system_datetime": now.isoformat(sep=" ", timespec="seconds"),
        "weekday_cn": weekday_cn,
        "latest_run_id": forecast.get("run_id") or "latest",
        "prediction_window": {
            "start": summary.get("forecast_start"),
            "end": summary.get("forecast_end"),
        },
        "data_window": {
            "start": min(latest_times) if latest_times else None,
            "end": max(latest_times) if latest_times else None,
        },
        "evidence": [{"source": "system_clock"}, {"source": "latest_forecast_summary"}],
    }

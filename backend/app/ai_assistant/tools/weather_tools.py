from __future__ import annotations

from typing import Any

from ...stage1_services import load_forecast, weather_forecast


def get_weather_summary(date: str | None = None, **_: Any) -> dict[str, Any]:
    payload = weather_forecast(date=date)
    return {"tool": "get_weather_summary", **payload}


def get_load_summary(date: str | None = None, **_: Any) -> dict[str, Any]:
    payload = load_forecast(date=date)
    return {"tool": "get_load_summary", **payload}

from __future__ import annotations

from typing import Any

from ...stage1_services import weather_forecast


def get_weather_summary(date: str | None = None, **_: Any) -> dict[str, Any]:
    payload = weather_forecast(date=date)
    return {"tool": "get_weather_summary", **payload}

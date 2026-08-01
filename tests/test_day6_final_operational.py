from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from prediction_engine.day6_operational import (
    BUSINESS_TIMEZONE,
    Day6OperationalError,
    build_feature_frame,
    feature_contract,
    feature_names,
    feature_specs,
    forecast_window,
    verify_24h_continuity,
)
from scripts.day6_provision_runtime import (
    GROUP_ROLE,
    LOGIN_ROLE,
    MODEL_TABLES,
    READ_TABLES,
    WRITE_TABLES,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _frames() -> tuple[pd.DatetimeIndex, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    anchor = pd.Timestamp("2026-08-01 10:00:00")
    targets = pd.date_range(anchor + pd.Timedelta(hours=1), periods=24, freq="h")
    price_times = pd.date_range(anchor - pd.Timedelta(days=15), anchor, freq="h")
    price = pd.DataFrame(
        {
            "datetime": price_times,
            "da_price": 30.0 + np.sin(np.arange(len(price_times)) / 24.0) * 8.0,
        }
    )
    load = pd.DataFrame(
        {"datetime": targets, "forecast_load": 16000.0 + np.arange(24, dtype="float64") * 25.0}
    )
    weather = pd.DataFrame(
        {
            "datetime": targets,
            "temperature_forecast": 25.0 + np.sin(np.arange(24) / 5.0),
            "humidity_forecast": 60.0 + np.arange(24) / 10.0,
            "wind_speed_forecast": 8.0 + np.arange(24) / 20.0,
            "precipitation_forecast": np.arange(24) / 100.0,
        }
    )
    return targets, price, load, weather


def test_online_safe_contract_is_strict_and_excludes_future_actuals() -> None:
    contract = feature_contract()
    specs = feature_specs()
    assert contract["feature_count"] == 31
    assert contract["timezone"] == BUSINESS_TIMEZONE
    assert contract["schema_hash"]
    assert feature_names() == [item.name for item in specs]
    forbidden = {"actual_load", "real_time_price", "rt_price", "future_actual_load", "future_target"}
    assert forbidden.isdisjoint(feature_names())
    assert all(item.availability in {"0h", "issued_before_anchor", "published_before_anchor"} for item in specs)
    assert all(item.dtype in {"int64", "float64"} for item in specs)


def test_feature_frame_uses_only_published_history_and_is_complete() -> None:
    targets, price, load, weather = _frames()
    frame = build_feature_frame(
        price_history=price,
        load_forecast=load,
        weather_forecast=weather,
        targets=targets,
    )
    assert frame.shape == (24, 31)
    assert list(frame.columns) == feature_names()
    assert not frame.isna().any().any()
    assert np.isfinite(frame.to_numpy(dtype="float64")).all()
    assert frame["da_price_lag_24"].iloc[-1] == pytest.approx(price["da_price"].iloc[-1])
    for spec in feature_specs():
        assert str(frame[spec.name].dtype) == spec.dtype


def test_feature_frame_fails_closed_when_provider_value_is_missing() -> None:
    targets, price, load, weather = _frames()
    load.loc[5, "forecast_load"] = np.nan
    with pytest.raises(Day6OperationalError, match="feature_missing_values:forecast_load"):
        build_feature_frame(
            price_history=price,
            load_forecast=load,
            weather_forecast=weather,
            targets=targets,
        )


def test_forecast_window_is_timezone_aware_and_contiguous() -> None:
    anchor, targets = forecast_window(
        datetime(2026, 8, 1, 10, 17, 9, tzinfo=ZoneInfo(BUSINESS_TIMEZONE))
    )
    assert anchor.minute == 17
    assert len(targets) == 24
    assert targets[0].hour == 11
    assert targets.tz is not None
    verify_24h_continuity(targets)


def test_runtime_role_contract_is_least_privilege() -> None:
    assert GROUP_ROLE == "beta10d_forecast_runtime"
    assert LOGIN_ROLE == "beta10d_forecast_login"
    assert READ_TABLES == ("raw_market", "raw_load", "raw_weather")
    assert MODEL_TABLES == ("model_registry",)
    assert WRITE_TABLES["audit_logs"] == ("INSERT",)
    assert "DELETE" not in {privilege for privileges in WRITE_TABLES.values() for privilege in privileges}


def test_forecast_frontend_binds_identity_to_current_run() -> None:
    service = (PROJECT_ROOT / "frontend/src/services/forecastApi.ts").read_text(encoding="utf-8")
    component = (PROJECT_ROOT / "frontend/src/components/forecast/ForecastDesign.tsx").read_text(encoding="utf-8")
    assert "const currentRun = forecastRunItems.find" in service
    assert "const modelVersion = currentRun?.model_version" in service
    assert "const featureVersion = currentRun?.feature_version" in service
    assert "developmentMode: Boolean(currentRun?.development_mode)" in service
    assert "inputBatchId: currentRun?.input_batch_id" in service
    assert "开发/演示闭环（非生产）" in component
    assert "Candidate · 开发演示" in component


def test_frontend_development_identity_is_read_only_and_build_gated() -> None:
    source = (PROJECT_ROOT / "frontend/src/api.ts").read_text(encoding="utf-8")
    assert "const AUTH_REQUIRED = String(import.meta.env.VITE_AUTH_REQUIRED ?? '1') !== '0'" in source
    assert "const DEVELOPMENT_IDENTITY_HEADERS" in source
    assert "'X-Role': 'developer'" in source
    assert "...DEVELOPMENT_IDENTITY_HEADERS" in source
    assert "'X-Role': 'admin'" not in source

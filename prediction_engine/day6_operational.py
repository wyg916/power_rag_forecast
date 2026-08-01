from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from pandas.tseries.holiday import USFederalHolidayCalendar

from fetch_power_market_data import build_session, discover_dataminer_subscription_key


BUSINESS_TIMEZONE = "America/New_York"
MARKET_REGION = "PJM_DOM"
PJM_PNODE_ID = 34964545
PJM_PNODE_NAME = "DOM"
PJM_LOAD_AREA = "DOMINION"
WEATHER_LOCATION = "Richmond, VA"
WEATHER_LATITUDE = 37.5407
WEATHER_LONGITUDE = -77.4360
CALENDAR_VERSION = "pandas_us_federal_calendar_v1"
PROVIDER_CONTRACT_VERSION = "day6_provider_contract_v1"
TARGET_FIELD = "da_price"
TIME_FIELD = "datetime"
PEAK_HOURS = frozenset({6, 7, 8, 9, 10, 11, 18, 19, 20, 21})
MORNING_PEAK_HOURS = frozenset({6, 7, 8, 9})
EVENING_PEAK_HOURS = frozenset({18, 19, 20, 21})


class Day6OperationalError(RuntimeError):
    pass


@dataclass(frozen=True)
class OperationalFeatureSpec:
    name: str
    dtype: str
    source_system: str
    availability: str
    derivation: str

    def public(self) -> dict[str, Any]:
        return {
            "feature_name": self.name,
            "dtype": self.dtype,
            "source_system": self.source_system,
            "availability_at_prediction_time": self.availability,
            "derivation": self.derivation,
            "online_safe": True,
        }


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def feature_specs() -> list[OperationalFeatureSpec]:
    integer_calendar = (
        "hour",
        "day_of_week",
        "month",
        "day",
        "day_of_year",
        "week_of_year",
        "is_weekend",
        "is_holiday",
        "is_morning_peak",
        "is_evening_peak",
        "is_peak_hour",
    )
    cyclic = ("hour_sin", "hour_cos", "dow_sin", "dow_cos", "month_sin", "month_cos")
    specs = [
        OperationalFeatureSpec(name, "int64", "deterministic_calendar", "0h", "target_datetime")
        for name in integer_calendar
    ]
    specs.extend(
        OperationalFeatureSpec(name, "float64", "deterministic_calendar", "0h", "cyclic_target_datetime")
        for name in cyclic
    )
    specs.extend(
        (
            OperationalFeatureSpec("forecast_load", "float64", "PJM_load_frcstd_7_day", "issued_before_anchor", "published_load_forecast"),
            OperationalFeatureSpec("temperature_forecast", "float64", "Open-Meteo", "issued_before_anchor", "temperature_2m"),
            OperationalFeatureSpec("humidity_forecast", "float64", "Open-Meteo", "issued_before_anchor", "relative_humidity_2m"),
            OperationalFeatureSpec("wind_speed_forecast", "float64", "Open-Meteo", "issued_before_anchor", "wind_speed_10m"),
            OperationalFeatureSpec("precipitation_forecast", "float64", "Open-Meteo", "issued_before_anchor", "precipitation"),
        )
    )
    for lag in (24, 48, 168):
        specs.append(
            OperationalFeatureSpec(
                f"da_price_lag_{lag}", "float64", "PJM_da_hrl_lmps", "published_before_anchor", f"exact_target_minus_{lag}h"
            )
        )
    for window in (24, 168):
        for aggregation in ("mean", "std"):
            specs.append(
                OperationalFeatureSpec(
                    f"da_price_anchor_{aggregation}_{window}",
                    "float64",
                    "PJM_da_hrl_lmps",
                    "published_before_anchor",
                    f"window_ending_target_minus_24h_{aggregation}",
                )
            )
    specs.extend(
        (
            OperationalFeatureSpec("da_price_same_hour_mean_7d", "float64", "PJM_da_hrl_lmps", "published_before_anchor", "seven_prior_days_same_hour_mean"),
            OperationalFeatureSpec("da_price_same_hour_std_7d", "float64", "PJM_da_hrl_lmps", "published_before_anchor", "seven_prior_days_same_hour_std"),
        )
    )
    if len(specs) != 31 or len({item.name for item in specs}) != len(specs):
        raise Day6OperationalError("operational_feature_manifest_invalid")
    return specs


def feature_names() -> list[str]:
    return [item.name for item in feature_specs()]


def feature_contract() -> dict[str, Any]:
    items = [item.public() for item in feature_specs()]
    schema_hash = canonical_sha256(items)
    return {
        "contract_version": "day6_operational_online_safe_v1",
        "feature_version": f"features_day6_operational_{schema_hash[:12]}",
        "schema_hash": schema_hash,
        "feature_count": len(items),
        "timezone": BUSINESS_TIMEZONE,
        "calendar_version": CALENDAR_VERSION,
        "features": items,
    }


def _normalize_local(values: Iterable[Any]) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(pd.to_datetime(list(values), errors="raise"))
    if index.tz is not None:
        index = index.tz_convert(BUSINESS_TIMEZONE).tz_localize(None)
    return index


def _calendar_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    local = _normalize_local(index)
    frame = pd.DataFrame(index=local)
    holidays = USFederalHolidayCalendar().holidays(start=local.min().normalize(), end=local.max().normalize())
    frame["hour"] = local.hour.astype("int64")
    frame["day_of_week"] = local.dayofweek.astype("int64")
    frame["month"] = local.month.astype("int64")
    frame["day"] = local.day.astype("int64")
    frame["day_of_year"] = local.dayofyear.astype("int64")
    frame["week_of_year"] = local.isocalendar().week.to_numpy(dtype="int64")
    frame["is_weekend"] = (local.dayofweek >= 5).astype("int64")
    frame["is_holiday"] = local.normalize().isin(holidays).astype("int64")
    frame["is_morning_peak"] = pd.Index(local.hour).isin(MORNING_PEAK_HOURS).astype("int64")
    frame["is_evening_peak"] = pd.Index(local.hour).isin(EVENING_PEAK_HOURS).astype("int64")
    frame["is_peak_hour"] = pd.Index(local.hour).isin(PEAK_HOURS).astype("int64")
    frame["hour_sin"] = np.sin(2 * np.pi * local.hour / 24)
    frame["hour_cos"] = np.cos(2 * np.pi * local.hour / 24)
    frame["dow_sin"] = np.sin(2 * np.pi * local.dayofweek / 7)
    frame["dow_cos"] = np.cos(2 * np.pi * local.dayofweek / 7)
    frame["month_sin"] = np.sin(2 * np.pi * local.month / 12)
    frame["month_cos"] = np.cos(2 * np.pi * local.month / 12)
    return frame


def _price_history_features(prices: pd.Series, targets: pd.DatetimeIndex) -> pd.DataFrame:
    series = prices.copy()
    series.index = _normalize_local(series.index)
    series = pd.to_numeric(series, errors="raise").groupby(level=0).last().sort_index()
    target_index = _normalize_local(targets)
    # Extend only the index, never the values, so lag/rolling operations can
    # materialize features for target hours up to anchor+24 from facts that end
    # at the prediction anchor.
    full_index = pd.date_range(series.index.min(), max(series.index.max(), target_index.max()), freq="h")
    series = series.reindex(full_index)
    output = pd.DataFrame(index=target_index)
    for lag in (24, 48, 168):
        output[f"da_price_lag_{lag}"] = series.reindex(target_index - pd.Timedelta(hours=lag)).to_numpy()
    shifted = series.shift(24)
    for window in (24, 168):
        rolling = shifted.rolling(window, min_periods=window)
        output[f"da_price_anchor_mean_{window}"] = rolling.mean().reindex(target_index).to_numpy()
        output[f"da_price_anchor_std_{window}"] = rolling.std().reindex(target_index).to_numpy()
    same_hour_values: list[list[float]] = []
    for target in target_index:
        same_hour_values.append([series.get(target - pd.Timedelta(days=day), np.nan) for day in range(1, 8)])
    same = np.asarray(same_hour_values, dtype="float64")
    output["da_price_same_hour_mean_7d"] = np.mean(same, axis=1)
    output["da_price_same_hour_std_7d"] = np.std(same, axis=1, ddof=1)
    return output


def _provider_frame(frame: pd.DataFrame, names: dict[str, str], targets: pd.DatetimeIndex) -> pd.DataFrame:
    if TIME_FIELD not in frame.columns:
        raise Day6OperationalError("provider_datetime_missing")
    source = frame.copy()
    source.index = _normalize_local(source[TIME_FIELD])
    source = source[~source.index.duplicated(keep="last")]
    result = pd.DataFrame(index=_normalize_local(targets))
    for source_name, output_name in names.items():
        if source_name not in source.columns:
            raise Day6OperationalError(f"provider_field_missing:{source_name}")
        result[output_name] = pd.to_numeric(source[source_name], errors="raise").reindex(result.index)
    return result


def build_feature_frame(
    *,
    price_history: pd.DataFrame,
    load_forecast: pd.DataFrame,
    weather_forecast: pd.DataFrame,
    targets: pd.DatetimeIndex,
    allow_missing: bool = False,
) -> pd.DataFrame:
    if not {TIME_FIELD, TARGET_FIELD} <= set(price_history.columns):
        raise Day6OperationalError("price_history_columns_missing")
    target_index = _normalize_local(targets)
    prices = pd.Series(
        pd.to_numeric(price_history[TARGET_FIELD], errors="raise").to_numpy(),
        index=_normalize_local(price_history[TIME_FIELD]),
        dtype="float64",
    )
    frame = _calendar_features(target_index)
    frame = frame.join(
        _provider_frame(load_forecast, {"forecast_load": "forecast_load"}, target_index),
        how="left",
    )
    frame = frame.join(
        _provider_frame(
            weather_forecast,
            {
                "temperature_forecast": "temperature_forecast",
                "humidity_forecast": "humidity_forecast",
                "wind_speed_forecast": "wind_speed_forecast",
                "precipitation_forecast": "precipitation_forecast",
            },
            target_index,
        ),
        how="left",
    )
    frame = frame.join(_price_history_features(prices, target_index), how="left")
    return validate_feature_frame(frame, allow_missing=allow_missing)


def build_training_frame(
    *,
    market: pd.DataFrame,
    load_forecast: pd.DataFrame,
    weather_forecast: pd.DataFrame,
) -> pd.DataFrame:
    market_data = market.copy()
    market_data.index = _normalize_local(market_data[TIME_FIELD])
    market_data = market_data[~market_data.index.duplicated(keep="last")].sort_index()
    targets = market_data.index
    features = build_feature_frame(
        price_history=market_data.reset_index(drop=True),
        load_forecast=load_forecast,
        weather_forecast=weather_forecast,
        targets=targets,
        allow_missing=True,
    )
    features[TARGET_FIELD] = pd.to_numeric(market_data[TARGET_FIELD], errors="raise").reindex(features.index)
    features.insert(0, TIME_FIELD, features.index)
    return features.reset_index(drop=True)


def validate_feature_frame(frame: pd.DataFrame, *, allow_missing: bool = False) -> pd.DataFrame:
    expected = feature_names()
    actual = list(frame.columns)
    if actual != expected:
        raise Day6OperationalError(f"feature_order_mismatch:expected={expected}:actual={actual}")
    if len(frame) == 0:
        raise Day6OperationalError("feature_frame_empty")
    if not allow_missing and frame.isna().any().any():
        missing = [name for name in expected if frame[name].isna().any()]
        raise Day6OperationalError(f"feature_missing_values:{','.join(missing)}")
    values = frame.to_numpy(dtype="float64")
    if not np.isfinite(values[~np.isnan(values)]).all():
        raise Day6OperationalError("feature_nonfinite")
    dtypes = {item.name: item.dtype for item in feature_specs()}
    return frame.astype(dtypes)


def forecast_window(anchor: datetime | None = None) -> tuple[datetime, pd.DatetimeIndex]:
    zone = ZoneInfo(BUSINESS_TIMEZONE)
    now = (anchor or datetime.now(zone)).astimezone(zone)
    floored = now.replace(minute=0, second=0, microsecond=0)
    start = floored + timedelta(hours=1)
    target_index = pd.date_range(start=start, periods=24, freq="h")
    return now, target_index


def _request_json(session: requests.Session, url: str, *, params: dict[str, Any]) -> tuple[dict[str, Any], str]:
    response = session.get(url, params=params, timeout=120)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise Day6OperationalError("provider_error")
    return payload, canonical_sha256(payload)


def fetch_live_weather(targets: pd.DatetimeIndex) -> tuple[pd.DataFrame, dict[str, Any]]:
    session = requests.Session()
    session.headers.update({"Accept": "application/json", "User-Agent": "PowerMarketForecast/Day6"})
    fetched_at = datetime.now(timezone.utc)
    payload, source_hash = _request_json(
        session,
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": WEATHER_LATITUDE,
            "longitude": WEATHER_LONGITUDE,
            "hourly": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
            "timezone": BUSINESS_TIMEZONE,
            "forecast_days": 3,
        },
    )
    hourly = payload.get("hourly") or {}
    frame = pd.DataFrame(
        {
            TIME_FIELD: pd.to_datetime(hourly.get("time") or []),
            "temperature_forecast": hourly.get("temperature_2m") or [],
            "humidity_forecast": hourly.get("relative_humidity_2m") or [],
            "precipitation_forecast": hourly.get("precipitation") or [],
            "wind_speed_forecast": hourly.get("wind_speed_10m") or [],
        }
    )
    selected = _provider_frame(
        frame,
        {
            "temperature_forecast": "temperature_forecast",
            "humidity_forecast": "humidity_forecast",
            "precipitation_forecast": "precipitation_forecast",
            "wind_speed_forecast": "wind_speed_forecast",
        },
        targets,
    ).reset_index(names=TIME_FIELD)
    metadata = {
        "source_name": "Open-Meteo Forecast API",
        "source_version": "best_match_live",
        "source_generated_at": fetched_at.isoformat(),
        "source_generated_at_semantics": "response_retrieval_time",
        "fetched_at": fetched_at.isoformat(),
        "valid_from": targets[0].isoformat(),
        "valid_to": targets[-1].isoformat(),
        "timezone": BUSINESS_TIMEZONE,
        "location": {"name": WEATHER_LOCATION, "latitude": WEATHER_LATITUDE, "longitude": WEATHER_LONGITUDE},
        "source_hash": source_hash,
        "row_count": len(selected),
    }
    return selected, metadata


def _pjm_session() -> requests.Session:
    key = discover_dataminer_subscription_key()
    return build_session(key)


def fetch_live_load_forecast(anchor: datetime, targets: pd.DatetimeIndex) -> tuple[pd.DataFrame, dict[str, Any]]:
    session = _pjm_session()
    fetched_at = datetime.now(timezone.utc)
    payload, source_hash = _request_json(
        session,
        "https://api.pjm.com/api/v1/load_frcstd_7_day",
        params={"rowCount": 5000, "startRow": 1},
    )
    items = pd.DataFrame(payload.get("items") or [])
    required = {
        "evaluated_at_datetime_ept",
        "forecast_datetime_beginning_ept",
        "forecast_area",
        "forecast_load_mw",
    }
    if items.empty or not required <= set(items.columns):
        raise Day6OperationalError("pjm_load_forecast_contract_invalid")
    items = items[items["forecast_area"].astype(str).str.upper() == PJM_LOAD_AREA]
    items["evaluated_at"] = pd.to_datetime(items["evaluated_at_datetime_ept"], errors="raise")
    items[TIME_FIELD] = pd.to_datetime(items["forecast_datetime_beginning_ept"], errors="raise")
    anchor_naive = anchor.astimezone(ZoneInfo(BUSINESS_TIMEZONE)).replace(tzinfo=None)
    items = items[items["evaluated_at"] <= anchor_naive]
    items = items.sort_values([TIME_FIELD, "evaluated_at"]).drop_duplicates(TIME_FIELD, keep="last")
    items["forecast_load"] = pd.to_numeric(items["forecast_load_mw"], errors="raise")
    selected = _provider_frame(items, {"forecast_load": "forecast_load"}, targets).reset_index(names=TIME_FIELD)
    issue_at = items["evaluated_at"].max()
    metadata = {
        "source_name": "PJM Data Miner load_frcstd_7_day",
        "source_version": PROVIDER_CONTRACT_VERSION,
        "source_generated_at": issue_at.isoformat() if pd.notna(issue_at) else fetched_at.isoformat(),
        "source_generated_at_semantics": "PJM evaluated_at_datetime_ept",
        "fetched_at": fetched_at.isoformat(),
        "valid_from": targets[0].isoformat(),
        "valid_to": targets[-1].isoformat(),
        "timezone": BUSINESS_TIMEZONE,
        "forecast_area": PJM_LOAD_AREA,
        "source_hash": source_hash,
        "row_count": len(selected),
    }
    return selected, metadata


def _date_range_text(start: date, end: date) -> str:
    return f"{start:%m/%d/%Y} 00:00to{end:%m/%d/%Y} 23:59"


def fetch_live_price_history(anchor: datetime, *, lookback_days: int = 14) -> tuple[pd.DataFrame, dict[str, Any]]:
    session = _pjm_session()
    fetched_at = datetime.now(timezone.utc)
    local_anchor = anchor.astimezone(ZoneInfo(BUSINESS_TIMEZONE))
    payload, source_hash = _request_json(
        session,
        "https://api.pjm.com/api/v1/da_hrl_lmps",
        params={
            "datetime_beginning_ept": _date_range_text((local_anchor - timedelta(days=lookback_days)).date(), local_anchor.date()),
            "pnode_id": PJM_PNODE_ID,
            "rowCount": 5000,
            "startRow": 1,
        },
    )
    items = pd.DataFrame(payload.get("items") or [])
    required = {"datetime_beginning_ept", "pnode_id", "total_lmp_da"}
    if items.empty or not required <= set(items.columns):
        raise Day6OperationalError("pjm_price_history_contract_invalid")
    items = items[pd.to_numeric(items["pnode_id"], errors="coerce") == PJM_PNODE_ID]
    items[TIME_FIELD] = pd.to_datetime(items["datetime_beginning_ept"], errors="raise")
    items[TARGET_FIELD] = pd.to_numeric(items["total_lmp_da"], errors="raise")
    if "version_nbr" in items.columns:
        items["version_nbr"] = pd.to_numeric(items["version_nbr"], errors="coerce")
        items = items.sort_values([TIME_FIELD, "version_nbr"])
    items = items.drop_duplicates(TIME_FIELD, keep="last")
    cutoff_naive = local_anchor.replace(tzinfo=None)
    items = items[items[TIME_FIELD] <= cutoff_naive][[TIME_FIELD, TARGET_FIELD]].sort_values(TIME_FIELD)
    if len(items) < 192:
        raise Day6OperationalError(f"pjm_price_history_insufficient:{len(items)}")
    metadata = {
        "source_name": "PJM Data Miner da_hrl_lmps",
        "source_version": PROVIDER_CONTRACT_VERSION,
        "source_generated_at": fetched_at.isoformat(),
        "source_generated_at_semantics": "API response retrieval time; values are published day-ahead facts",
        "fetched_at": fetched_at.isoformat(),
        "valid_from": items[TIME_FIELD].min().isoformat(),
        "valid_to": items[TIME_FIELD].max().isoformat(),
        "timezone": BUSINESS_TIMEZONE,
        "pnode_id": PJM_PNODE_ID,
        "pnode_name": PJM_PNODE_NAME,
        "source_hash": source_hash,
        "row_count": len(items),
    }
    return items.reset_index(drop=True), metadata


def fetch_previous_day_weather(start: date, end: date) -> tuple[pd.DataFrame, dict[str, Any]]:
    session = requests.Session()
    session.headers.update({"Accept": "application/json", "User-Agent": "PowerMarketForecast/Day6Training"})
    chunks: list[pd.DataFrame] = []
    hashes: list[str] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=89))
        payload, source_hash = _request_json(
            session,
            "https://previous-runs-api.open-meteo.com/v1/forecast",
            params={
                "latitude": WEATHER_LATITUDE,
                "longitude": WEATHER_LONGITUDE,
                "start_date": cursor.isoformat(),
                "end_date": chunk_end.isoformat(),
                "hourly": (
                    "temperature_2m_previous_day1,relative_humidity_2m_previous_day1,"
                    "precipitation_previous_day1,wind_speed_10m_previous_day1"
                ),
                "timezone": BUSINESS_TIMEZONE,
            },
        )
        hourly = payload.get("hourly") or {}
        chunks.append(
            pd.DataFrame(
                {
                    TIME_FIELD: pd.to_datetime(hourly.get("time") or []),
                    "temperature_forecast": hourly.get("temperature_2m_previous_day1") or [],
                    "humidity_forecast": hourly.get("relative_humidity_2m_previous_day1") or [],
                    "precipitation_forecast": hourly.get("precipitation_previous_day1") or [],
                    "wind_speed_forecast": hourly.get("wind_speed_10m_previous_day1") or [],
                }
            )
        )
        hashes.append(source_hash)
        cursor = chunk_end + timedelta(days=1)
    frame = pd.concat(chunks, ignore_index=True).drop_duplicates(TIME_FIELD, keep="last").sort_values(TIME_FIELD)
    metadata = {
        "source_name": "Open-Meteo Previous Runs API",
        "source_version": "previous_day1_fixed_24h_lead",
        "source_generated_at": datetime.now(timezone.utc).isoformat(),
        "source_generated_at_semantics": "training retrieval time",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "valid_from": frame[TIME_FIELD].min().isoformat(),
        "valid_to": frame[TIME_FIELD].max().isoformat(),
        "timezone": BUSINESS_TIMEZONE,
        "source_hash": canonical_sha256(hashes),
        "chunk_count": len(hashes),
        "row_count": len(frame),
        "lead_time_hours": 24,
    }
    return frame.reset_index(drop=True), metadata


def verify_24h_continuity(index: pd.DatetimeIndex) -> None:
    values = pd.DatetimeIndex(index)
    if len(values) != 24 or values.tz is None or values.has_duplicates:
        raise Day6OperationalError("forecast_window_invalid")
    deltas = values.to_series(index=range(len(values))).diff().dropna()
    if not bool((deltas == pd.Timedelta(hours=1)).all()):
        raise Day6OperationalError("forecast_window_not_contiguous")
    if any(not math.isfinite(float(item)) for item in values.asi8):
        raise Day6OperationalError("forecast_window_nonfinite")

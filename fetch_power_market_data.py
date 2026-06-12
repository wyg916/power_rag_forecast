from __future__ import annotations

import calendar
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests
from pandas.tseries.holiday import USFederalHolidayCalendar
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from zoneinfo import ZoneInfo

from automation_common import load_config
from database_utils import sync_core_datasets_to_database


PJM_BASE_URL = "https://api.pjm.com/api/v1"
PJM_DATAMINER_SETTINGS_URL = "https://dataminer2.pjm.com/config/settings.json"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

OUTPUT_DIR = Path("output")
ZONE_NAME = "DOM"
PNODE_ID = 34964545
PNODE_NAME = "DOM"
WEATHER_POINT_NAME = "Richmond, Virginia"
WEATHER_LAT = 37.5407
WEATHER_LON = -77.4360
WEATHER_MODEL = "era5"
TIMEZONE_NAME = "America/New_York"
HISTORY_MONTHS = 24
INCREMENTAL_BUFFER_DAYS = 3
PLACEHOLDER_MARKET_KEYS = {"", "your_key", "your_pjm_subscription_key_here"}


@dataclass(frozen=True)
class DatasetConfig:
    name: str
    endpoint: str
    filters: dict[str, str | int | bool]


def apply_market_config(config: dict) -> str:
    global ZONE_NAME, PNODE_ID, PNODE_NAME, WEATHER_POINT_NAME, WEATHER_LAT, WEATHER_LON, TIMEZONE_NAME

    market = config.get("market", {})
    ZONE_NAME = str(market.get("pjm_region", ZONE_NAME) or ZONE_NAME)
    PNODE_ID = int(market.get("pjm_node_id", PNODE_ID) or PNODE_ID)
    PNODE_NAME = str(market.get("pjm_node_name", PNODE_NAME) or PNODE_NAME)
    WEATHER_POINT_NAME = str(market.get("weather_point_name", WEATHER_POINT_NAME) or WEATHER_POINT_NAME)
    WEATHER_LAT = float(market.get("weather_lat", WEATHER_LAT) or WEATHER_LAT)
    WEATHER_LON = float(market.get("weather_lon", WEATHER_LON) or WEATHER_LON)
    TIMEZONE_NAME = str(market.get("timezone", TIMEZONE_NAME) or TIMEZONE_NAME)
    return resolve_pjm_subscription_key(market)


def _usable_subscription_key(value: str | None) -> str:
    key = str(value or "").strip()
    return "" if key.lower() in PLACEHOLDER_MARKET_KEYS else key


def _as_bool(value: object, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def resolve_pjm_subscription_key(market: dict) -> str:
    configured = _usable_subscription_key(market.get("pjm_subscription_key") or os.environ.get("PJM_SUBSCRIPTION_KEY", ""))
    if configured:
        print("PJM Data Miner API Key 来源：.env / 系统环境变量 / 配置文件。")
        return configured

    if not _as_bool(market.get("pjm_auto_discover_subscription_key"), True):
        raise RuntimeError("未配置 PJM_SUBSCRIPTION_KEY，且已关闭自动发现。请在 .env 或系统环境变量中设置 PJM_SUBSCRIPTION_KEY=your_key。")

    discovered = discover_dataminer_subscription_key(str(market.get("pjm_settings_url") or PJM_DATAMINER_SETTINGS_URL))
    print("PJM Data Miner API Key 来源：Data Miner 2 公开前端配置自动发现。")
    return discovered


def discover_dataminer_subscription_key(settings_url: str = PJM_DATAMINER_SETTINGS_URL) -> str:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "Accept": "application/json,text/plain,*/*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PowerMarketForecast/2.5",
        }
    )
    response = session.get(settings_url, timeout=30)
    response.raise_for_status()
    payload = response.json()
    key = _usable_subscription_key(payload.get("subscriptionKey"))
    if not key:
        raise RuntimeError(
            "未配置 PJM_SUBSCRIPTION_KEY，且无法从 Data Miner 2 公开配置自动发现 subscriptionKey。"
            "请登录 https://apiportal.pjm.com/ 获取 Primary key，并写入 .env。"
        )
    return key


def build_session(subscription_key: str) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "Ocp-Apim-Subscription-Key": subscription_key,
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PowerMarketForecast/2.5",
        }
    )
    return session


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def last_complete_eastern_day() -> date:
    eastern_today = datetime.now(ZoneInfo(TIMEZONE_NAME)).date()
    return eastern_today - timedelta(days=1)


def month_chunks(start_date: date, end_date: date) -> Iterable[tuple[date, date]]:
    cursor = date(start_date.year, start_date.month, 1)
    while cursor <= end_date:
        _, last_day = calendar.monthrange(cursor.year, cursor.month)
        chunk_start = max(start_date, cursor)
        chunk_end = min(end_date, date(cursor.year, cursor.month, last_day))
        yield chunk_start, chunk_end
        cursor = add_months(cursor, 1)


def format_pjm_datetime_range(start_date: date, end_date: date) -> str:
    return f"{start_date:%m/%d/%Y} 00:00to{end_date:%m/%d/%Y} 23:59"


def fetch_paginated_json(
    session: requests.Session,
    url: str,
    params: dict[str, str | int | bool] | None = None,
) -> list[dict]:
    items: list[dict] = []
    next_url = url
    next_params = params

    while next_url:
        response = session.get(next_url, params=next_params, timeout=120)
        response.raise_for_status()
        payload = response.json()
        items.extend(payload.get("items", []))
        next_url = next(
            (link["href"] for link in payload.get("links", []) if link.get("rel") == "next"),
            None,
        )
        next_params = None

    return items


def fetch_pjm_feed(
    session: requests.Session,
    config: DatasetConfig,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    endpoint_url = f"{PJM_BASE_URL}/{config.endpoint}"

    for chunk_start, chunk_end in month_chunks(start_date, end_date):
        params: dict[str, str | int | bool] = {
            "rowCount": 50000,
            "startRow": 1,
            **config.filters,
        }

        date_filter_name = (
            "evaluated_at_ept"
            if config.endpoint == "load_frcstd_hist"
            else "datetime_beginning_ept"
        )
        params[date_filter_name] = format_pjm_datetime_range(chunk_start, chunk_end)

        records = fetch_paginated_json(session, endpoint_url, params=params)
        if records:
            frames.append(pd.DataFrame(records))

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    return combined.drop_duplicates().reset_index(drop=True)


def read_existing_xlsx(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        if path.stat().st_size <= 0:
            print(f"WARNING: 跳过空历史缓存文件：{path.name}")
            return pd.DataFrame()
        return pd.read_excel(path, engine="openpyxl")
    except Exception as exc:
        print(f"WARNING: 跳过无法读取的历史缓存文件：{path.name}，原因：{exc}")
        return pd.DataFrame()


def get_incremental_start_date(
    existing_df: pd.DataFrame,
    datetime_col: str,
    fallback_start_date: date,
    buffer_days: int = INCREMENTAL_BUFFER_DAYS,
) -> date:
    if existing_df.empty or datetime_col not in existing_df.columns:
        return fallback_start_date
    dt_series = pd.to_datetime(existing_df[datetime_col], errors="coerce").dropna()
    if dt_series.empty:
        return fallback_start_date
    candidate = (dt_series.max() - pd.Timedelta(days=buffer_days)).date()
    return max(candidate, fallback_start_date)


def merge_and_deduplicate(existing_df: pd.DataFrame, new_df: pd.DataFrame, subset: list[str] | None = None) -> pd.DataFrame:
    if existing_df.empty:
        combined = new_df.copy()
    elif new_df.empty:
        combined = existing_df.copy()
    else:
        combined = pd.concat([existing_df, new_df], ignore_index=True)
    if combined.empty:
        return combined
    combined = combined.drop_duplicates(subset=subset).reset_index(drop=True)
    return combined


def trim_by_datetime(df: pd.DataFrame, datetime_col: str, start_date: date) -> pd.DataFrame:
    if df.empty or datetime_col not in df.columns:
        return df
    output = df.copy()
    output[datetime_col] = pd.to_datetime(output[datetime_col], errors="coerce")
    cutoff = pd.Timestamp(start_date)
    return output.loc[output[datetime_col] >= cutoff].reset_index(drop=True)


def fetch_weather(start_date: date, end_date: date) -> pd.DataFrame:
    params = {
        "latitude": WEATHER_LAT,
        "longitude": WEATHER_LON,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "hourly": "temperature_2m,wind_speed_10m,precipitation",
        "timezone": TIMEZONE_NAME,
        "models": WEATHER_MODEL,
    }
    response = requests.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=120)
    response.raise_for_status()
    payload = response.json()
    hourly = payload["hourly"]

    df = pd.DataFrame(
        {
            "datetime": pd.to_datetime(hourly["time"]),
            "temperature": hourly["temperature_2m"],
            "wind_speed": hourly["wind_speed_10m"],
            "precipitation": hourly["precipitation"],
            "latitude": payload["latitude"],
            "longitude": payload["longitude"],
            "weather_model": WEATHER_MODEL,
            "weather_point_name": WEATHER_POINT_NAME,
        }
    )

    weather_columns = ["temperature", "wind_speed", "precipitation"]
    if df[weather_columns].isna().any().any():
        fallback_params = dict(params)
        fallback_params["models"] = "best_match"
        fallback_response = requests.get(OPEN_METEO_ARCHIVE_URL, params=fallback_params, timeout=120)
        fallback_response.raise_for_status()
        fallback_payload = fallback_response.json()
        fallback_df = pd.DataFrame(
            {
                "datetime": pd.to_datetime(fallback_payload["hourly"]["time"]),
                "temperature": fallback_payload["hourly"]["temperature_2m"],
                "wind_speed": fallback_payload["hourly"]["wind_speed_10m"],
                "precipitation": fallback_payload["hourly"]["precipitation"],
            }
        )
        fallback_df = fallback_df.set_index("datetime")
        df = df.set_index("datetime")

        filled_mask = pd.Series(False, index=df.index)
        for column in weather_columns:
            column_fill_mask = df[column].isna() & fallback_df[column].notna()
            if column_fill_mask.any():
                df.loc[column_fill_mask, column] = fallback_df.loc[column_fill_mask, column]
                filled_mask = filled_mask | column_fill_mask

        df.loc[filled_mask, "weather_model"] = "best_match_backfill"
        df = df.reset_index()

    return df.drop_duplicates().sort_values("datetime").reset_index(drop=True)


def standardize_da_prices(df: pd.DataFrame) -> pd.DataFrame:
    output = df.rename(
        columns={
            "datetime_beginning_ept": "datetime",
            "datetime_beginning_utc": "datetime_utc",
            "pnode_id": "node_id",
            "pnode_name": "node_name",
            "total_lmp_da": "da_price",
            "congestion_price_da": "da_congestion_price",
            "marginal_loss_price_da": "da_marginal_loss_price",
            "system_energy_price_da": "da_system_energy_price",
        }
    )[
        [
            "datetime",
            "datetime_utc",
            "node_id",
            "node_name",
            "da_price",
            "da_congestion_price",
            "da_marginal_loss_price",
            "da_system_energy_price",
            "type",
            "row_is_current",
            "version_nbr",
        ]
    ].copy()
    output["datetime"] = pd.to_datetime(output["datetime"])
    output["datetime_utc"] = pd.to_datetime(output["datetime_utc"])
    return output.sort_values("datetime").drop_duplicates(subset=["datetime", "node_id"]).reset_index(drop=True)


def standardize_rt_prices(df: pd.DataFrame) -> pd.DataFrame:
    output = df.rename(
        columns={
            "datetime_beginning_ept": "datetime",
            "datetime_beginning_utc": "datetime_utc",
            "pnode_id": "node_id",
            "pnode_name": "node_name",
            "total_lmp_rt": "rt_price",
            "congestion_price_rt": "rt_congestion_price",
            "marginal_loss_price_rt": "rt_marginal_loss_price",
            "system_energy_price_rt": "rt_system_energy_price",
        }
    )[
        [
            "datetime",
            "datetime_utc",
            "node_id",
            "node_name",
            "rt_price",
            "rt_congestion_price",
            "rt_marginal_loss_price",
            "rt_system_energy_price",
            "type",
            "row_is_current",
            "version_nbr",
        ]
    ].copy()
    output["datetime"] = pd.to_datetime(output["datetime"])
    output["datetime_utc"] = pd.to_datetime(output["datetime_utc"])
    return output.sort_values("datetime").drop_duplicates(subset=["datetime", "node_id"]).reset_index(drop=True)


def standardize_actual_load(df: pd.DataFrame) -> pd.DataFrame:
    output = df.rename(
        columns={
            "datetime_beginning_ept": "datetime",
            "datetime_beginning_utc": "datetime_utc",
            "mw": "actual_load",
        }
    )[
        [
            "datetime",
            "datetime_utc",
            "load_area",
            "zone",
            "mkt_region",
            "nerc_region",
            "actual_load",
            "is_verified",
        ]
    ].copy()
    output["datetime"] = pd.to_datetime(output["datetime"])
    output["datetime_utc"] = pd.to_datetime(output["datetime_utc"])
    return output.sort_values("datetime").drop_duplicates(subset=["datetime", "load_area"]).reset_index(drop=True)


def standardize_forecast_load(df: pd.DataFrame) -> pd.DataFrame:
    output = df.rename(
        columns={
            "evaluated_at_ept": "forecast_evaluated_at",
            "evaluated_at_utc": "forecast_evaluated_at_utc",
            "forecast_hour_beginning_ept": "datetime",
            "forecast_hour_beginning_utc": "datetime_utc",
            "forecast_load_mw": "forecast_load",
        }
    )[
        [
            "forecast_evaluated_at",
            "forecast_evaluated_at_utc",
            "datetime",
            "datetime_utc",
            "forecast_area",
            "forecast_load",
        ]
    ].copy()
    output["forecast_evaluated_at"] = pd.to_datetime(output["forecast_evaluated_at"])
    output["forecast_evaluated_at_utc"] = pd.to_datetime(output["forecast_evaluated_at_utc"])
    output["datetime"] = pd.to_datetime(output["datetime"])
    output["datetime_utc"] = pd.to_datetime(output["datetime_utc"])
    return output.sort_values(["datetime", "forecast_evaluated_at"]).drop_duplicates().reset_index(drop=True)


def choose_day_ahead_forecast(forecast_df: pd.DataFrame) -> pd.DataFrame:
    working = forecast_df.copy()
    working["target_date"] = working["datetime"].dt.normalize()
    working["preferred_eval_date"] = working["target_date"] - pd.Timedelta(days=1)
    working["eval_date"] = working["forecast_evaluated_at"].dt.normalize()

    preferred = (
        working.loc[working["eval_date"] == working["preferred_eval_date"]]
        .sort_values(["datetime", "forecast_evaluated_at"])
        .groupby("datetime", as_index=False)
        .tail(1)
    )

    missing_datetimes = set(working["datetime"]) - set(preferred["datetime"])
    fallback = (
        working.loc[
            working["datetime"].isin(missing_datetimes)
            & (working["forecast_evaluated_at"] < working["datetime"])
        ]
        .sort_values(["datetime", "forecast_evaluated_at"])
        .groupby("datetime", as_index=False)
        .tail(1)
    )

    selected = (
        pd.concat([preferred, fallback], ignore_index=True)
        .sort_values("datetime")
        .drop_duplicates(subset=["datetime"], keep="last")
        .reset_index(drop=True)
    )

    return selected[
        [
            "datetime",
            "datetime_utc",
            "forecast_area",
            "forecast_load",
            "forecast_evaluated_at",
            "forecast_evaluated_at_utc",
        ]
    ]


def build_master_table(
    da_df: pd.DataFrame,
    load_df: pd.DataFrame,
    forecast_selected_df: pd.DataFrame,
    weather_df: pd.DataFrame,
    rt_df: pd.DataFrame,
) -> pd.DataFrame:
    master = da_df.copy()
    master = master.merge(
        load_df[["datetime", "actual_load", "load_area", "mkt_region", "nerc_region", "is_verified"]],
        on="datetime",
        how="left",
    )
    master = master.merge(
        forecast_selected_df[
            [
                "datetime",
                "forecast_load",
                "forecast_area",
                "forecast_evaluated_at",
                "forecast_evaluated_at_utc",
            ]
        ],
        on="datetime",
        how="left",
    )
    master = master.merge(
        weather_df[["datetime", "temperature", "wind_speed", "precipitation"]],
        on="datetime",
        how="left",
    )
    master = master.merge(
        rt_df[
            [
                "datetime",
                "rt_price",
                "rt_congestion_price",
                "rt_marginal_loss_price",
                "rt_system_energy_price",
            ]
        ],
        on="datetime",
        how="left",
    )

    master["price_spread_rt_minus_da"] = master["rt_price"] - master["da_price"]
    master["hour"] = master["datetime"].dt.hour
    master["day_of_week"] = master["datetime"].dt.dayofweek
    master["month"] = master["datetime"].dt.month
    master["year"] = master["datetime"].dt.year
    master["is_weekend"] = master["day_of_week"].isin([5, 6])
    master["season"] = master["month"].map(
        {
            12: "winter",
            1: "winter",
            2: "winter",
            3: "spring",
            4: "spring",
            5: "spring",
            6: "summer",
            7: "summer",
            8: "summer",
            9: "autumn",
            10: "autumn",
            11: "autumn",
        }
    )

    holiday_calendar = USFederalHolidayCalendar()
    holiday_dates = holiday_calendar.holidays(
        start=master["datetime"].min().normalize(),
        end=master["datetime"].max().normalize(),
    )
    master["is_holiday"] = master["datetime"].dt.normalize().isin(holiday_dates)
    master["region_id"] = ZONE_NAME
    master["weather_source"] = f"Open-Meteo Historical Weather API ({WEATHER_MODEL})"

    ordered_columns = [
        "datetime",
        "datetime_utc",
        "region_id",
        "node_id",
        "node_name",
        "da_price",
        "da_congestion_price",
        "da_marginal_loss_price",
        "da_system_energy_price",
        "rt_price",
        "rt_congestion_price",
        "rt_marginal_loss_price",
        "rt_system_energy_price",
        "price_spread_rt_minus_da",
        "actual_load",
        "forecast_load",
        "forecast_evaluated_at",
        "forecast_evaluated_at_utc",
        "load_area",
        "forecast_area",
        "mkt_region",
        "nerc_region",
        "temperature",
        "wind_speed",
        "precipitation",
        "hour",
        "day_of_week",
        "month",
        "year",
        "season",
        "is_weekend",
        "is_holiday",
        "is_verified",
        "weather_source",
    ]

    return master[ordered_columns].sort_values("datetime").reset_index(drop=True)


def to_excel_datetime_columns(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column]):
            output[column] = output[column].dt.tz_localize(None)
    return output


def write_dataset(path: Path, df: pd.DataFrame, sheet_name: str = "data") -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        to_excel_datetime_columns(df).to_excel(writer, sheet_name=sheet_name, index=False)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int_or_none(name: str) -> int | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        print(f"WARNING: {name} is not a valid integer, ignored.")
        return None


def _sync_legacy_core_datasets(data_dir: Path, config: dict[str, Any]) -> None:
    try:
        sync_core_datasets_to_database(data_dir, config, log=print)
    except Exception as exc:
        print(f"WARNING: Legacy core dataset sync failed and was skipped: {exc}")


def sync_stage1_raw_to_postgres() -> dict[str, Any]:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    enabled = _env_bool("POWER_MARKET_SYNC_STAGE1_POSTGRES", bool(database_url))
    if not enabled:
        print("INFO: Stage1 raw PostgreSQL sync skipped. Set POWER_MARKET_SYNC_STAGE1_POSTGRES=1 and DATABASE_URL to enable it.")
        return {"status": "skipped", "reason": "disabled"}
    if not database_url:
        print("WARNING: Stage1 raw PostgreSQL sync skipped because DATABASE_URL is not set.")
        return {"status": "skipped", "reason": "missing_database_url"}

    from scripts.import_stage1_raw_data_to_postgres import run_import

    replace = _env_bool("POWER_MARKET_STAGE1_REPLACE", True)
    strict = _env_bool("POWER_MARKET_STAGE1_STRICT", False)
    limit = _env_int_or_none("POWER_MARKET_STAGE1_LIMIT")
    try:
        result = run_import(dry_run=False, replace=replace, limit=limit)
    except Exception as exc:
        if strict:
            raise
        print(f"WARNING: Stage1 raw PostgreSQL sync failed and was skipped: {exc}")
        return {"status": "failed", "error": str(exc)}

    status = result.get("status", "unknown")
    total_rows = result.get("total_rows", 0)
    print(f"SUCCESS: Stage1 raw PostgreSQL sync finished. status={status}, rows={total_rows}, replace={replace}")
    for item in result.get("results", []):
        print(
            "  - {table}: status={status}, rows={rows}".format(
                table=item.get("table") or item.get("name"),
                status=item.get("status"),
                rows=item.get("rows", 0),
            )
        )
    if strict and status not in {"ok"}:
        raise RuntimeError(f"Stage1 raw PostgreSQL sync did not finish cleanly: {status}")
    return result


def sync_generated_datasets_to_databases(data_dir: Path, config: dict[str, Any]) -> None:
    _sync_legacy_core_datasets(data_dir, config)
    sync_stage1_raw_to_postgres()


def build_field_dictionary() -> pd.DataFrame:
    rows = [
        ("da_price_raw", "datetime", "小时前电价的本地时间戳，PJM EPT", "datetime", "PJM Data Miner 2", ""),
        ("da_price_raw", "da_price", "日前总 LMP", "USD/MWh", "PJM Data Miner 2", ""),
        ("da_price_raw", "da_congestion_price", "日前拥塞分量", "USD/MWh", "PJM Data Miner 2", ""),
        ("da_price_raw", "da_marginal_loss_price", "日前边际损耗分量", "USD/MWh", "PJM Data Miner 2", ""),
        ("da_price_raw", "da_system_energy_price", "日前系统能量分量", "USD/MWh", "PJM Data Miner 2", ""),
        ("actual_load_raw", "actual_load", "小时实际负荷", "MW", "PJM Data Miner 2", "DOM 负荷区"),
        ("forecast_load_raw", "forecast_load", "历史负荷预测值", "MW", "PJM Data Miner 2", "按固定日提前版本筛选"),
        ("forecast_load_raw", "forecast_evaluated_at", "预测发布时间，EPT", "datetime", "PJM Data Miner 2", ""),
        ("weather_raw", "temperature", "2 米气温", "°C", "Open-Meteo Historical API / ERA5", WEATHER_POINT_NAME),
        ("weather_raw", "wind_speed", "10 米风速", "km/h", "Open-Meteo Historical API / ERA5", WEATHER_POINT_NAME),
        ("weather_raw", "precipitation", "逐小时降水", "mm", "Open-Meteo Historical API / ERA5", f"{WEATHER_POINT_NAME}; 最近缺口由 best_match 回填"),
        ("rt_price_raw", "rt_price", "实时总 LMP", "USD/MWh", "PJM Data Miner 2", "可选增强数据"),
        ("master_table", "datetime", "主表小时粒度时间戳，EPT", "datetime", "Merged", ""),
        ("master_table", "region_id", "区域标识", "text", "Derived", ZONE_NAME),
        ("master_table", "da_price", "预测目标变量", "USD/MWh", "PJM Data Miner 2", ""),
        ("master_table", "actual_load", "小时实际负荷", "MW", "PJM Data Miner 2", ""),
        ("master_table", "forecast_load", "用于日前建模的固定版本负荷预测", "MW", "PJM Data Miner 2", ""),
        ("master_table", "temperature", "小时气温", "°C", "Open-Meteo Historical API / ERA5", ""),
        ("master_table", "wind_speed", "小时风速", "km/h", "Open-Meteo Historical API / ERA5", ""),
        ("master_table", "precipitation", "小时降水", "mm", "Open-Meteo Historical API / ERA5", ""),
        ("master_table", "weather_source", "天气数据来源标记", "text", "Derived", "era5 或 best_match_backfill"),
        ("master_table", "is_holiday", "美国联邦节假日标记", "bool", "Derived", "用于日期特征"),
    ]
    return pd.DataFrame(
        rows,
        columns=["dataset", "field_name", "meaning", "unit", "source", "notes"],
    )


def build_coverage_summary(datasets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for name, df in datasets.items():
        summary: dict[str, object] = {
            "dataset": name,
            "rows": len(df),
            "columns": len(df.columns),
            "start_datetime": None,
            "end_datetime": None,
            "duplicate_rows": int(df.duplicated().sum()),
            "total_missing_cells": int(df.isna().sum().sum()),
        }
        if "datetime" in df.columns:
            summary["start_datetime"] = df["datetime"].min()
            summary["end_datetime"] = df["datetime"].max()
        rows.append(summary)
    return pd.DataFrame(rows)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config()
    try:
        pjm_subscription_key = apply_market_config(config)
    except RuntimeError as exc:
        print(f"WARNING: {exc}")
        print("WARNING: 跳过 PJM 外部数据刷新，复用本地数据并尝试同步数据库。")
        try:
            forecast_raw_path = OUTPUT_DIR / "forecast_load_raw.xlsx"
            forecast_selected_path = OUTPUT_DIR / "forecast_load_selected.xlsx"
            if (
                forecast_raw_path.exists()
                and forecast_raw_path.stat().st_size > 0
                and (not forecast_selected_path.exists() or forecast_selected_path.stat().st_size <= 0)
            ):
                forecast_df = pd.read_excel(forecast_raw_path, engine="openpyxl")
                selected_df = choose_day_ahead_forecast(forecast_df)
                if not selected_df.empty:
                    write_dataset(forecast_selected_path, selected_df)
                    print(f"SUCCESS: 已修复 forecast_load_selected.xlsx，记录数：{len(selected_df)}")
            sync_generated_datasets_to_databases(OUTPUT_DIR, config)
        except Exception as fallback_exc:
            print(f"WARNING: 本地数据降级同步未完成：{fallback_exc}")
        return

    end_date = last_complete_eastern_day()
    start_date = add_months(end_date + timedelta(days=1), -HISTORY_MONTHS)
    forecast_start_date = start_date - timedelta(days=1)

    session = build_session(pjm_subscription_key)

    da_config = DatasetConfig(
        name="da_price_raw",
        endpoint="da_hrl_lmps",
        filters={"pnode_id": PNODE_ID, "row_is_current": "true"},
    )
    rt_config = DatasetConfig(
        name="rt_price_raw",
        endpoint="rt_hrl_lmps",
        filters={"pnode_id": PNODE_ID, "row_is_current": "true"},
    )
    actual_load_config = DatasetConfig(
        name="actual_load_raw",
        endpoint="hrl_load_metered",
        filters={"load_area": ZONE_NAME},
    )
    forecast_config = DatasetConfig(
        name="forecast_load_raw",
        endpoint="load_frcstd_hist",
        filters={"forecast_area": ZONE_NAME},
    )

    print(f"目标维护时间范围: {start_date} 到 {end_date} ({TIMEZONE_NAME})")

    existing_da = read_existing_xlsx(OUTPUT_DIR / "da_price_raw.xlsx")
    existing_rt = read_existing_xlsx(OUTPUT_DIR / "rt_price_raw.xlsx")
    existing_load = read_existing_xlsx(OUTPUT_DIR / "actual_load_raw.xlsx")
    existing_forecast = read_existing_xlsx(OUTPUT_DIR / "forecast_load_raw.xlsx")
    existing_weather = read_existing_xlsx(OUTPUT_DIR / "weather_raw.xlsx")

    da_fetch_start = get_incremental_start_date(existing_da, "datetime", start_date)
    rt_fetch_start = get_incremental_start_date(existing_rt, "datetime", start_date)
    load_fetch_start = get_incremental_start_date(existing_load, "datetime", start_date)
    forecast_fetch_start = get_incremental_start_date(existing_forecast, "forecast_evaluated_at", forecast_start_date)
    weather_fetch_start = get_incremental_start_date(existing_weather, "datetime", start_date)

    print(f"日前电价增量抓取起点: {da_fetch_start}")
    print(f"实时电价增量抓取起点: {rt_fetch_start}")
    print(f"实际负荷增量抓取起点: {load_fetch_start}")
    print(f"负荷预测增量抓取起点: {forecast_fetch_start}")
    print(f"天气增量抓取起点: {weather_fetch_start}")

    da_raw = fetch_pjm_feed(session, da_config, da_fetch_start, end_date)
    rt_raw = fetch_pjm_feed(session, rt_config, rt_fetch_start, end_date)
    load_raw = fetch_pjm_feed(session, actual_load_config, load_fetch_start, end_date)
    forecast_raw = fetch_pjm_feed(session, forecast_config, forecast_fetch_start, end_date)
    weather_raw = fetch_weather(weather_fetch_start, end_date)

    da_df = merge_and_deduplicate(
        trim_by_datetime(existing_da, "datetime", start_date),
        standardize_da_prices(da_raw),
        subset=["datetime", "node_id"],
    ).sort_values("datetime").reset_index(drop=True)
    rt_df = merge_and_deduplicate(
        trim_by_datetime(existing_rt, "datetime", start_date),
        standardize_rt_prices(rt_raw),
        subset=["datetime", "node_id"],
    ).sort_values("datetime").reset_index(drop=True)
    load_df = merge_and_deduplicate(
        trim_by_datetime(existing_load, "datetime", start_date),
        standardize_actual_load(load_raw),
        subset=["datetime", "load_area"],
    ).sort_values("datetime").reset_index(drop=True)
    forecast_df = merge_and_deduplicate(
        trim_by_datetime(existing_forecast, "datetime", forecast_start_date),
        standardize_forecast_load(forecast_raw),
        subset=["forecast_evaluated_at", "datetime", "forecast_area"],
    ).sort_values(["datetime", "forecast_evaluated_at"]).reset_index(drop=True)
    forecast_selected_df = choose_day_ahead_forecast(forecast_df)
    forecast_selected_df = forecast_selected_df.loc[
        forecast_selected_df["datetime"].between(
            pd.Timestamp(start_date),
            pd.Timestamp(end_date) + pd.Timedelta(hours=23),
        )
    ].reset_index(drop=True)
    weather_df = merge_and_deduplicate(
        trim_by_datetime(existing_weather, "datetime", start_date),
        weather_raw,
        subset=["datetime"],
    ).sort_values("datetime").reset_index(drop=True)

    master_df = build_master_table(da_df, load_df, forecast_selected_df, weather_df, rt_df)
    weather_complete_end = weather_df.loc[
        weather_df[["temperature", "wind_speed", "precipitation"]].notna().all(axis=1),
        "datetime",
    ].max()
    complete_end = min(
        da_df["datetime"].max(),
        load_df["datetime"].max(),
        rt_df["datetime"].max(),
        forecast_selected_df["datetime"].max(),
        weather_complete_end,
    )
    master_df = master_df.loc[master_df["datetime"] <= complete_end].reset_index(drop=True)
    core_columns = [
        "da_price",
        "actual_load",
        "forecast_load",
        "temperature",
        "wind_speed",
        "precipitation",
    ]
    master_df = master_df.dropna(subset=core_columns).reset_index(drop=True)

    datasets = {
        "da_price_raw": da_df,
        "rt_price_raw": rt_df,
        "actual_load_raw": load_df,
        "forecast_load_raw": forecast_df,
        "forecast_load_selected": forecast_selected_df,
        "weather_raw": weather_df,
        "master_table": master_df,
    }

    for dataset_name, dataframe in datasets.items():
        write_dataset(OUTPUT_DIR / f"{dataset_name}.xlsx", dataframe)

    field_dictionary = build_field_dictionary()
    coverage_summary = build_coverage_summary(datasets)
    source_summary = pd.DataFrame(
        [
            {
                "dataset": "PJM Day-Ahead Hourly LMPs",
                "source_url": "https://dataminer2.pjm.com/feed/da_hrl_lmps/definition",
                "selected_region_or_node": f"{PNODE_NAME} ({PNODE_ID})",
            },
            {
                "dataset": "PJM Real-Time Hourly LMPs",
                "source_url": "https://dataminer2.pjm.com/feed/rt_hrl_lmps/definition",
                "selected_region_or_node": f"{PNODE_NAME} ({PNODE_ID})",
            },
            {
                "dataset": "PJM Hourly Load Metered",
                "source_url": "https://dataminer2.pjm.com/feed/hrl_load_metered/definition",
                "selected_region_or_node": ZONE_NAME,
            },
            {
                "dataset": "PJM Historical Load Forecasts",
                "source_url": "https://dataminer2.pjm.com/feed/load_frcstd_hist/definition",
                "selected_region_or_node": ZONE_NAME,
            },
            {
                "dataset": "Open-Meteo Historical Weather API (ERA5)",
                "source_url": "https://open-meteo.com/en/docs/historical-weather-api",
                "selected_region_or_node": WEATHER_POINT_NAME,
            },
        ]
    )

    with pd.ExcelWriter(OUTPUT_DIR / "data_dictionary.xlsx", engine="openpyxl") as writer:
        field_dictionary.to_excel(writer, sheet_name="fields", index=False)
        to_excel_datetime_columns(coverage_summary).to_excel(writer, sheet_name="coverage", index=False)
        source_summary.to_excel(writer, sheet_name="sources", index=False)

    print("文件已生成:")
    for path in sorted(OUTPUT_DIR.glob("*.xlsx")):
        print(path.resolve())
    sync_generated_datasets_to_databases(OUTPUT_DIR, config)
    print("数据已按“已有本地数据 + 最新增量 + 去重 + 最近24个月保留”口径完成更新，并已同步到数据库。")


if __name__ == "__main__":
    main()

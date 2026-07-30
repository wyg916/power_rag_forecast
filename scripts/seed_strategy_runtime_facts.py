from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import make_url, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import get_settings
from backend.app.db.session import create_app_engine


BATCH_ID = "p6_strategy_runtime_20260726_v1"
DATA_SOURCE = "business_rule_simulation"
SCENARIO = "zhejiang_day_ahead_storage_arbitrage"
LOCAL_ZONE = ZoneInfo("Asia/Shanghai")


def _assert_unique_database() -> None:
    url = make_url(get_settings().database_url)
    if (
        (url.database or "") != "postgres"
        or (url.host or "") not in {"localhost", "127.0.0.1", "::1"}
        or (url.port or 5432) != 5432
        or (url.username or "") != "postgres"
    ):
        raise RuntimeError("database_target_must_be_localhost_5432_postgres")


def _devices(generated_at: datetime) -> list[dict]:
    common = {
        "data_source": DATA_SOURCE,
        "is_simulated": True,
        "batch_id": BATCH_ID,
        "generated_at": generated_at,
        "scenario": SCENARIO,
    }
    return [
        {
            **common,
            "device_id": "SIM-ESS-HZ-001",
            "device_name": "杭州东部储能单元 A",
            "station_name": "杭州东部综合能源站",
            "region": "浙江省",
            "rated_capacity_mwh": Decimal("100.000"),
            "rated_power_mw": Decimal("50.000"),
            "charge_efficiency": Decimal("0.9200"),
            "discharge_efficiency": Decimal("0.9100"),
            "soc_lower_pct": Decimal("15.000"),
            "soc_upper_pct": Decimal("90.000"),
            "operating_status": "online",
        },
        {
            **common,
            "device_id": "SIM-ESS-NB-002",
            "device_name": "宁波港区储能单元 B",
            "station_name": "宁波港区能源站",
            "region": "浙江省",
            "rated_capacity_mwh": Decimal("60.000"),
            "rated_power_mw": Decimal("30.000"),
            "charge_efficiency": Decimal("0.9000"),
            "discharge_efficiency": Decimal("0.9000"),
            "soc_lower_pct": Decimal("20.000"),
            "soc_upper_pct": Decimal("88.000"),
            "operating_status": "online",
        },
    ]


def _soc_rows(devices: list[dict], generated_at: datetime) -> list[dict]:
    start = generated_at.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
    profiles = {
        "SIM-ESS-HZ-001": [46, 44, 42, 40, 42, 48, 56, 64, 72, 78, 76, 72, 69, 66, 62, 58, 54, 50, 46, 43, 48, 55, 61, 67],
        "SIM-ESS-NB-002": [51, 49, 47, 45, 44, 49, 55, 61, 68, 73, 71, 69, 66, 63, 60, 56, 52, 48, 45, 43, 47, 52, 57, 62],
    }
    device_map = {item["device_id"]: item for item in devices}
    rows: list[dict] = []
    for device_id, values in profiles.items():
        device = device_map[device_id]
        capacity = Decimal(str(device["rated_capacity_mwh"]))
        previous = values[0]
        for index, soc in enumerate(values):
            delta = soc - previous
            mode = "charging" if delta > 0 else "discharging" if delta < 0 else "idle"
            active_power = Decimal(str(round(abs(delta) * float(capacity) / 100, 3)))
            if mode == "charging":
                active_power = -active_power
            rows.append(
                {
                    "snapshot_id": f"{BATCH_ID}_{device_id}_{index:02d}",
                    "device_id": device_id,
                    "observed_at": start + timedelta(hours=index),
                    "soc_pct": Decimal(str(soc)),
                    "available_energy_mwh": (capacity * Decimal(str(soc)) / Decimal("100")).quantize(Decimal("0.001")),
                    "active_power_mw": active_power,
                    "operating_mode": mode,
                    "data_source": DATA_SOURCE,
                    "is_simulated": True,
                    "batch_id": BATCH_ID,
                    "generated_at": generated_at,
                    "scenario": SCENARIO,
                }
            )
            previous = soc
    return rows


def _execution_rows(generated_at: datetime) -> list[dict]:
    base = generated_at.replace(minute=0, second=0, microsecond=0)
    common = {
        "strategy_id": None,
        "currency": "CNY",
        "settlement_method": "day_ahead_spread_estimate",
        "data_source": DATA_SOURCE,
        "is_simulated": True,
        "batch_id": BATCH_ID,
        "generated_at": generated_at,
        "scenario": SCENARIO,
    }
    specs = [
        ("001", "SIM-ESS-HZ-001", -18, "charge", 36, 34.8, 36, 34.2, 42, 72, "completed", "低价窗口充电完成，功率与 SOC 变化在设备约束内。", 28600),
        ("002", "SIM-ESS-HZ-001", -12, "discharge", 42, 40.5, 42, 39.8, 76, 54, "completed", "高价窗口放电完成，执行偏差 3.6%。", 51200),
        ("003", "SIM-ESS-NB-002", -17, "charge", 24, 23.1, 24, 22.4, 44, 68, "completed", "低价补能完成，充电效率符合模拟设备参数。", 17300),
        ("004", "SIM-ESS-NB-002", -8, "discharge", 26, 25.0, 26, 24.1, 71, 48, "completed", "晚高峰放电完成，未出现越限。", 32400),
        ("005", "SIM-ESS-HZ-001", -1, "charge", 30, 18.0, 30, 12.0, 61, 67, "in_progress", "当前处于受控模拟充电窗口，仅记录反馈，不下发设备指令。", None),
        ("006", "SIM-ESS-NB-002", 2, "discharge", 22, None, 22, None, 62, None, "scheduled", "等待计划窗口；本系统不自动执行或控制设备。", None),
    ]
    rows: list[dict] = []
    for code, device_id, offset, action, planned_power, actual_power, planned_energy, actual_energy, soc_before, soc_after, status, feedback, revenue in specs:
        rows.append(
            {
                **common,
                "execution_id": f"{BATCH_ID}_exec_{code}",
                "device_id": device_id,
                "window_start_at": base + timedelta(hours=offset),
                "window_end_at": base + timedelta(hours=offset + 1),
                "action": action,
                "planned_power_mw": Decimal(str(planned_power)),
                "actual_power_mw": None if actual_power is None else Decimal(str(actual_power)),
                "planned_energy_mwh": Decimal(str(planned_energy)),
                "actual_energy_mwh": None if actual_energy is None else Decimal(str(actual_energy)),
                "soc_before_pct": Decimal(str(soc_before)),
                "soc_after_pct": None if soc_after is None else Decimal(str(soc_after)),
                "execution_status": status,
                "feedback_message": feedback,
                "realized_revenue_cny": None if revenue is None else Decimal(str(revenue)),
            }
        )
    return rows


def seed() -> dict[str, int | str]:
    _assert_unique_database()
    generated_at = datetime.now(LOCAL_ZONE)
    devices = _devices(generated_at)
    snapshots = _soc_rows(devices, generated_at)
    executions = _execution_rows(generated_at)
    engine = create_app_engine()
    with engine.begin() as conn:
        for row in devices:
            conn.execute(
                text(
                    """
                    INSERT INTO storage_devices (
                        device_id,device_name,station_name,region,rated_capacity_mwh,rated_power_mw,
                        charge_efficiency,discharge_efficiency,soc_lower_pct,soc_upper_pct,operating_status,
                        data_source,is_simulated,batch_id,generated_at,scenario
                    ) VALUES (
                        :device_id,:device_name,:station_name,:region,:rated_capacity_mwh,:rated_power_mw,
                        :charge_efficiency,:discharge_efficiency,:soc_lower_pct,:soc_upper_pct,:operating_status,
                        :data_source,:is_simulated,:batch_id,:generated_at,:scenario
                    )
                    ON CONFLICT (device_id) DO UPDATE SET
                        device_name=EXCLUDED.device_name,station_name=EXCLUDED.station_name,region=EXCLUDED.region,
                        rated_capacity_mwh=EXCLUDED.rated_capacity_mwh,rated_power_mw=EXCLUDED.rated_power_mw,
                        charge_efficiency=EXCLUDED.charge_efficiency,discharge_efficiency=EXCLUDED.discharge_efficiency,
                        soc_lower_pct=EXCLUDED.soc_lower_pct,soc_upper_pct=EXCLUDED.soc_upper_pct,
                        operating_status=EXCLUDED.operating_status,generated_at=EXCLUDED.generated_at,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE storage_devices.is_simulated IS TRUE AND storage_devices.batch_id=EXCLUDED.batch_id
                    """
                ),
                row,
            )
        for row in snapshots:
            conn.execute(
                text(
                    """
                    INSERT INTO storage_soc_snapshots (
                        snapshot_id,device_id,observed_at,soc_pct,available_energy_mwh,active_power_mw,
                        operating_mode,data_source,is_simulated,batch_id,generated_at,scenario
                    ) VALUES (
                        :snapshot_id,:device_id,:observed_at,:soc_pct,:available_energy_mwh,:active_power_mw,
                        :operating_mode,:data_source,:is_simulated,:batch_id,:generated_at,:scenario
                    )
                    ON CONFLICT (snapshot_id) DO UPDATE SET
                        observed_at=EXCLUDED.observed_at,soc_pct=EXCLUDED.soc_pct,
                        available_energy_mwh=EXCLUDED.available_energy_mwh,active_power_mw=EXCLUDED.active_power_mw,
                        operating_mode=EXCLUDED.operating_mode,generated_at=EXCLUDED.generated_at,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE storage_soc_snapshots.is_simulated IS TRUE
                      AND storage_soc_snapshots.batch_id=EXCLUDED.batch_id
                    """
                ),
                row,
            )
        for row in executions:
            conn.execute(
                text(
                    """
                    INSERT INTO strategy_execution_items (
                        execution_id,strategy_id,device_id,window_start_at,window_end_at,action,
                        planned_power_mw,actual_power_mw,planned_energy_mwh,actual_energy_mwh,
                        soc_before_pct,soc_after_pct,execution_status,feedback_message,
                        realized_revenue_cny,currency,settlement_method,data_source,is_simulated,
                        batch_id,generated_at,scenario
                    ) VALUES (
                        :execution_id,:strategy_id,:device_id,:window_start_at,:window_end_at,:action,
                        :planned_power_mw,:actual_power_mw,:planned_energy_mwh,:actual_energy_mwh,
                        :soc_before_pct,:soc_after_pct,:execution_status,:feedback_message,
                        :realized_revenue_cny,:currency,:settlement_method,:data_source,:is_simulated,
                        :batch_id,:generated_at,:scenario
                    )
                    ON CONFLICT (execution_id) DO UPDATE SET
                        window_start_at=EXCLUDED.window_start_at,window_end_at=EXCLUDED.window_end_at,
                        planned_power_mw=EXCLUDED.planned_power_mw,actual_power_mw=EXCLUDED.actual_power_mw,
                        planned_energy_mwh=EXCLUDED.planned_energy_mwh,actual_energy_mwh=EXCLUDED.actual_energy_mwh,
                        soc_before_pct=EXCLUDED.soc_before_pct,soc_after_pct=EXCLUDED.soc_after_pct,
                        execution_status=EXCLUDED.execution_status,feedback_message=EXCLUDED.feedback_message,
                        realized_revenue_cny=EXCLUDED.realized_revenue_cny,generated_at=EXCLUDED.generated_at,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE strategy_execution_items.is_simulated IS TRUE
                      AND strategy_execution_items.batch_id=EXCLUDED.batch_id
                    """
                ),
                row,
            )
        counts = {
            table_name: conn.execute(
                text(f"SELECT count(*) FROM {table_name} WHERE batch_id=:batch_id AND is_simulated IS TRUE"),
                {"batch_id": BATCH_ID},
            ).scalar_one()
            for table_name in ("storage_devices", "storage_soc_snapshots", "strategy_execution_items")
        }
        if counts != {
            "storage_devices": len(devices),
            "storage_soc_snapshots": len(snapshots),
            "strategy_execution_items": len(executions),
        }:
            raise RuntimeError("simulation_batch_validation_failed")
    return {"batch_id": BATCH_ID, **counts}


def rollback() -> dict[str, int | str]:
    _assert_unique_database()
    engine = create_app_engine()
    deleted: dict[str, int | str] = {"batch_id": BATCH_ID}
    with engine.begin() as conn:
        for table_name in ("strategy_execution_items", "storage_soc_snapshots", "storage_devices"):
            result = conn.execute(
                text(f"DELETE FROM {table_name} WHERE batch_id=:batch_id AND is_simulated IS TRUE"),
                {"batch_id": BATCH_ID},
            )
            deleted[table_name] = int(result.rowcount or 0)
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description="P6 策略运行事实受控模拟入库工具")
    parser.add_argument("--rollback-batch", action="store_true", help=f"仅回滚模拟批次 {BATCH_ID}")
    args = parser.parse_args()
    result = rollback() if args.rollback_batch else seed()
    print("strategy_runtime_seed_ok", result)


if __name__ == "__main__":
    main()

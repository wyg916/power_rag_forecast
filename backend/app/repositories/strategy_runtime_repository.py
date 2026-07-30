from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app.repositories.base import postgres_engine


RUNTIME_FACT_STALE_AFTER = timedelta(hours=6)


def _public(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_public(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def latest_runtime_generated_at(items: list[dict[str, Any]]) -> datetime | None:
    latest: datetime | None = None
    for item in items:
        value = item.get("generated_at")
        if isinstance(value, datetime) and (latest is None or value > latest):
            latest = value
    return latest


def evaluate_runtime_freshness(generated_at: Any, *, now: datetime) -> tuple[bool, float | None]:
    if not isinstance(generated_at, datetime):
        return True, None
    normalized_generated_at = (
        generated_at.replace(tzinfo=timezone.utc)
        if generated_at.tzinfo is None
        else generated_at.astimezone(timezone.utc)
    )
    normalized_now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    age_seconds = (normalized_now - normalized_generated_at).total_seconds()
    return age_seconds > RUNTIME_FACT_STALE_AFTER.total_seconds(), age_seconds


def get_strategy_runtime_facts(*, engine: Engine | None = None) -> dict[str, Any]:
    active_engine = engine or postgres_engine()
    if active_engine is None:
        raise RuntimeError("strategy_runtime_database_unavailable")

    with active_engine.connect() as conn:
        devices = [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT *
                    FROM storage_devices
                    ORDER BY operating_status='online' DESC, device_name, device_id
                    """
                )
            ).mappings()
        ]
        snapshots = [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT *
                    FROM storage_soc_snapshots
                    ORDER BY device_id, observed_at
                    """
                )
            ).mappings()
        ]
        executions = [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT execution_id, strategy_id, device_id, window_start_at, window_end_at,
                           action, planned_power_mw, actual_power_mw, planned_energy_mwh,
                           actual_energy_mwh, soc_before_pct, soc_after_pct, execution_status,
                           feedback_message, realized_revenue_cny, currency, settlement_method,
                           data_source, is_simulated, batch_id, generated_at, scenario
                    FROM strategy_execution_items
                    ORDER BY window_start_at DESC, execution_id
                    """
                )
            ).mappings()
        ]

    series_by_device: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        series_by_device[str(snapshot["device_id"])].append(snapshot)

    runtime_items = [*devices, *snapshots, *executions]
    latest_generated_at = latest_runtime_generated_at(runtime_items)
    is_stale, _ = evaluate_runtime_freshness(latest_generated_at, now=datetime.now(timezone.utc))
    simulated_count = sum(1 for item in runtime_items if item.get("is_simulated"))
    fact_count = len(devices) + len(snapshots) + len(executions)
    if not fact_count:
        source_type = "unavailable"
        source_label = "运行事实未入库"
    elif simulated_count == fact_count:
        source_type = "simulated"
        source_label = "业务规则模拟入库"
    elif simulated_count:
        source_type = "mixed"
        source_label = "真实与模拟入库混合"
    else:
        source_type = "real"
        source_label = "设备运行事实"

    completed = [item for item in executions if item.get("execution_status") == "completed"]
    realized_revenue = sum(Decimal(str(item.get("realized_revenue_cny") or 0)) for item in completed)
    device_items: list[dict[str, Any]] = []
    for device in devices:
        device_id = str(device["device_id"])
        series = series_by_device.get(device_id, [])
        latest_soc = series[-1] if series else None
        device_items.append({**device, "latest_soc": latest_soc, "soc_series": series})

    batch_ids = sorted({str(item.get("batch_id")) for item in [*devices, *snapshots, *executions] if item.get("batch_id")})
    scenarios = sorted({str(item.get("scenario")) for item in [*devices, *snapshots, *executions] if item.get("scenario")})
    return _public(
        {
            "available": bool(device_items and snapshots),
            "source_type": source_type,
            "source_label": source_label,
            "is_simulated": bool(fact_count and simulated_count == fact_count),
            "is_stale": is_stale,
            "stale_reason": "runtime_facts_older_than_6h" if is_stale and fact_count else None,
            "generated_at": latest_generated_at,
            "batch_ids": batch_ids,
            "scenarios": scenarios,
            "devices": device_items,
            "execution_items": executions,
            "summary": {
                "device_count": len(device_items),
                "online_device_count": sum(1 for item in devices if item.get("operating_status") == "online"),
                "execution_count": len(executions),
                "completed_count": len(completed),
                "in_progress_count": sum(1 for item in executions if item.get("execution_status") == "in_progress"),
                "scheduled_count": sum(1 for item in executions if item.get("execution_status") == "scheduled"),
                "failed_count": sum(1 for item in executions if item.get("execution_status") == "failed"),
                "realized_revenue_cny": realized_revenue,
            },
        }
    )

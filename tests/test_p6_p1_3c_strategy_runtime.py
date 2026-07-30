from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import make_url, text

from backend.app.core.config import get_settings
from backend.app.db.session import create_app_engine
from backend.app.repositories.strategy_runtime_repository import (
    RUNTIME_FACT_STALE_AFTER,
    evaluate_runtime_freshness,
    get_strategy_runtime_facts,
    latest_runtime_generated_at,
)
from scripts.seed_strategy_runtime_facts import BATCH_ID, seed


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _table_snapshot() -> dict[str, tuple[int, str]]:
    with create_app_engine().connect() as conn:
        return {
            table_name: (
                int(row["rows_count"]),
                str(row["content_hash"]),
            )
            for table_name in (
                "strategy_advice",
                "strategy_reviews",
                "model_strategy_memory",
                "storage_devices",
                "storage_soc_snapshots",
                "strategy_execution_items",
                "audit_logs",
                "task_runs",
                "task_logs",
            )
            for row in (
                conn.execute(
                    text(
                        f"""
                        SELECT COUNT(*) AS rows_count,
                               MD5(COALESCE(STRING_AGG(
                                   ROW_TO_JSON(t)::text,
                                   '|' ORDER BY ROW_TO_JSON(t)::text
                               ), '')) AS content_hash
                        FROM "{table_name}" AS t
                        """
                    )
                ).mappings().one(),
            )
        }


def test_unique_database_target_and_migration_head() -> None:
    url = make_url(get_settings().database_url)
    assert (url.database or "") == "postgres"
    assert (url.host or "") in {"localhost", "127.0.0.1", "::1"}
    assert (url.port or 5432) == 5432
    assert (url.username or "") == "postgres"
    with create_app_engine().connect() as conn:
        assert conn.execute(text("SELECT current_database()")).scalar_one() == "postgres"
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0016_strategy_runtime"


def test_controlled_seed_is_idempotent_and_traceable() -> None:
    first = seed()
    second = seed()
    assert first == second
    assert first == {
        "batch_id": BATCH_ID,
        "storage_devices": 2,
        "storage_soc_snapshots": 48,
        "strategy_execution_items": 6,
    }
    with create_app_engine().connect() as conn:
        for table_name, expected in (
            ("storage_devices", 2),
            ("storage_soc_snapshots", 48),
            ("strategy_execution_items", 6),
        ):
            row = conn.execute(
                text(
                    f"""
                    SELECT count(*) AS total,
                           count(*) FILTER (WHERE is_simulated IS TRUE) AS simulated,
                           count(*) FILTER (
                               WHERE data_source='business_rule_simulation'
                                 AND batch_id=:batch_id
                                 AND scenario='zhejiang_day_ahead_storage_arbitrage'
                                 AND generated_at IS NOT NULL
                           ) AS traceable
                    FROM {table_name}
                    """
                ),
                {"batch_id": BATCH_ID},
            ).mappings().one()
            assert dict(row) == {"total": expected, "simulated": expected, "traceable": expected}


def test_runtime_read_chain_has_no_write_side_effect() -> None:
    before = _table_snapshot()
    payload = get_strategy_runtime_facts(engine=create_app_engine())
    after = _table_snapshot()
    assert after == before
    assert payload["available"] is True
    assert payload["source_type"] == "simulated"
    assert payload["source_label"] == "业务规则模拟入库"
    assert payload["is_simulated"] is True
    generated_at = datetime.fromisoformat(payload["generated_at"])
    expected_stale, _ = evaluate_runtime_freshness(generated_at, now=datetime.now(timezone.utc))
    assert payload["is_stale"] is expected_stale
    assert payload["stale_reason"] == ("runtime_facts_older_than_6h" if expected_stale else None)
    assert len(payload["devices"]) == 2
    assert sum(len(item["soc_series"]) for item in payload["devices"]) == 48
    assert len(payload["execution_items"]) == 6
    assert payload["summary"]["completed_count"] == 4
    assert payload["summary"]["realized_revenue_cny"] == 129500.0


@pytest.mark.parametrize(
    ("generated_at", "expected"),
    [
        (datetime(2026, 7, 30, 5, 0, tzinfo=timezone.utc), False),
        (datetime(2026, 7, 30, 4, 0, tzinfo=timezone.utc), False),
        (datetime(2026, 7, 30, 3, 59, 59, 999999, tzinfo=timezone.utc), True),
        (None, True),
        ("invalid-timestamp", True),
    ],
)
def test_runtime_freshness_semantics(generated_at: object, expected: bool) -> None:
    now = datetime(2026, 7, 30, 10, 0, tzinfo=timezone.utc)
    is_stale, age_seconds = evaluate_runtime_freshness(generated_at, now=now)
    assert is_stale is expected
    if isinstance(generated_at, datetime):
        assert age_seconds is not None
    else:
        assert age_seconds is None


def test_runtime_freshness_threshold_and_timestamp_selection_are_explicit() -> None:
    now = datetime(2026, 7, 30, 10, 0, tzinfo=timezone.utc)
    assert RUNTIME_FACT_STALE_AFTER == timedelta(hours=6)
    assert latest_runtime_generated_at(
        [
            {"generated_at": "invalid-timestamp"},
            {"generated_at": None},
            {"generated_at": now - timedelta(hours=2)},
            {"generated_at": now - timedelta(hours=1)},
        ]
    ) == now - timedelta(hours=1)
    assert latest_runtime_generated_at([{"generated_at": "invalid-timestamp"}]) is None


def test_runtime_api_is_read_only_and_permission_guarded() -> None:
    source = _read("backend/app/api/v1/endpoints/strategy.py")
    assert '@router.get("/api/strategy/runtime-facts")' in source
    assert 'require_permission("strategy:read")' in source
    route_block = source.split('@router.get("/api/strategy/runtime-facts")', 1)[1].split('@router.get("/api/strategy/config")', 1)[0]
    assert "@router.post" not in route_block
    assert "get_strategy_runtime_facts" in route_block


def test_frontend_uses_runtime_api_without_static_soc_fallback() -> None:
    api_source = _read("frontend/src/api.ts")
    service_source = _read("frontend/src/services/strategyApi.ts")
    design_source = _read("frontend/src/components/strategy/StrategyDesign.tsx")
    assert "strategyRuntimeFacts" in api_source
    assert "api.strategyRuntimeFacts" in service_source
    assert "soc_series" in service_source
    assert "execution_items" in service_source
    assert "if (value == null || value === '') return null" in service_source
    assert "derivedSoc" not in service_source
    assert "参数化 SOC" not in design_source
    assert "当前 SOC 未接入" not in design_source
    assert "实际执行收益</span><strong>待回填" not in design_source
    assert "Math.random" not in service_source


def test_old_stale_information_box_is_removed_but_stale_reason_remains() -> None:
    states_source = _read("frontend/src/components/common/States.tsx")
    assert "当前展示的是可追溯旧数据" not in states_source
    assert "page-state-stale-inline" in states_source
    assert "meta.staleReason" in states_source
    assert "模拟入库" in states_source

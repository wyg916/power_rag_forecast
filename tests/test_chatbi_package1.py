from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.chatbi.catalog import CATALOG_SUMMARY, DIMENSION_CATALOG, JOIN_CATALOG, METRIC_CATALOG
from backend.app.chatbi.contracts import AnalysisPlan
from backend.app.chatbi.validator import validate_analysis_plan


def plan(**overrides) -> AnalysisPlan:
    payload = {
        "datasets": ["market_price_history"],
        "metrics": ["avg_day_ahead_price"],
        "dimensions": ["market_observed_at", "market_code"],
        "group_by": ["market_code"],
        "time_range": {"start": "2026-06-01T00:00:00", "end": "2026-06-18T23:00:00"},
        "time_grain": "day",
        "order_by": [{"field": "avg_day_ahead_price", "direction": "desc"}],
        "chart_intent": "bar",
    }
    payload.update(overrides)
    return AnalysisPlan.model_validate(payload)


def test_catalog_is_frozen_against_registered_fields() -> None:
    assert CATALOG_SUMMARY == {"version": "chatbi-v1.0.0", "metrics": 13, "dimensions": 21, "joins": 2}
    assert all(item.formula.startswith("AVG(") and item.status == "active" for item in METRIC_CATALOG.values())
    assert all(item.dataset and item.field and item.permission == "data:read" for item in DIMENSION_CATALOG.values())
    assert {item.join_type for item in JOIN_CATALOG.values()} == {"inner"}


def test_analysis_plan_hash_is_stable_and_id_is_not_part_of_hash() -> None:
    first, second = plan(), plan()
    assert first.analysis_plan_id != second.analysis_plan_id
    assert first.stable_hash() == second.stable_hash()


@pytest.mark.parametrize("payload", [
    {"datasets": ["market_price_history"], "metrics": ["avg_day_ahead_price"], "rogue_sql": "select 1"},
    {"datasets": ["market_price_history", "market_price_history"], "metrics": ["avg_day_ahead_price"]},
    {"datasets": ["market_price_history"], "metrics": ["avg_day_ahead_price"], "limit": 501},
    {"datasets": [], "metrics": [], "clarification_required": True},
])
def test_analysis_plan_contract_fails_closed(payload: dict) -> None:
    with pytest.raises(ValidationError):
        AnalysisPlan.model_validate(payload)


def test_validator_accepts_registered_single_dataset_plan() -> None:
    result = validate_analysis_plan(plan(), permissions=("data:read",))
    assert result.valid and result.executable and result.issues == ()


@pytest.mark.parametrize(("overrides", "code"), [
    ({"metrics": ["invented_metric"]}, "unregistered_metric"),
    ({"dimensions": ["invented_dimension"]}, "unregistered_dimension"),
    ({"group_by": ["market_code"], "dimensions": ["market_observed_at"]}, "group_by_not_selected"),
    ({"comparison": "yoy", "time_range": None}, "comparison_time_range_required"),
    ({"chart_intent": "pie", "group_by": []}, "pie_semantics_invalid"),
])
def test_validator_rejects_invalid_semantics(overrides: dict, code: str) -> None:
    result = validate_analysis_plan(plan(**overrides), permissions=("data:read",))
    assert not result.valid and code in {item.code for item in result.issues}


def test_validator_requires_permissions_and_whitelist_join() -> None:
    denied = validate_analysis_plan(plan(), permissions=())
    assert "dataset_forbidden" in {item.code for item in denied.issues}
    joined = plan(
        datasets=["market_price_history", "load_history"],
        metrics=["avg_day_ahead_price", "avg_actual_load"],
        dimensions=["market_observed_at", "market_code", "load_market_code"],
        group_by=["market_code"],
        joins=["market_load_by_time_market"],
    )
    assert validate_analysis_plan(joined, permissions=("data:read",)).valid
    missing_join = joined.model_copy(update={"joins": []})
    assert "join_required" in {item.code for item in validate_analysis_plan(missing_join, permissions=("data:read",)).issues}


def test_clarification_plan_is_not_executable() -> None:
    ambiguous = AnalysisPlan(clarification_required=True, clarification_question="请确认要分析市场电价还是预测电价？")
    result = validate_analysis_plan(ambiguous, permissions=("data:read",))
    assert result.status == "clarification_required" and not result.executable and not result.valid


def test_0022_is_the_only_successor_and_has_scoped_grants() -> None:
    source = Path("migrations/versions/0022_chatbi_semantic_analysis_v1.py").read_text(encoding="utf-8")
    assert 'revision = "0022_chatbi_semantic_v1"' in source
    assert 'down_revision = "0021_memory_lifecycle_v1"' in source
    for table in ("chatbi_metric_catalog", "chatbi_dimension_catalog", "chatbi_join_catalog", "chatbi_analysis_plans"):
        assert f"CREATE TABLE {table}" in source and f"DROP TABLE {table}" in source
    assert "GRANT DELETE" not in source and "TRUNCATE" not in source

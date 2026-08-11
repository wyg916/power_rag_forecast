from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from backend.app.chatbi.compiler import QueryCompileError, compile_analysis_plan
from backend.app.chatbi.contracts import AnalysisPlan
from backend.app.chatbi.validator import validate_analysis_plan
from backend.app.db.session import get_engine


def plan(**overrides) -> AnalysisPlan:
    payload = {
        "datasets": ["market_price_history"],
        "metrics": ["avg_day_ahead_price"],
        "dimensions": ["market_observed_at", "market_code"],
        "group_by": ["market_code"],
        "time_range": {"start": "2020-01-01T00:00:00", "end": "2020-01-01T23:00:00"},
        "order_by": [{"field": "avg_day_ahead_price", "direction": "desc"}],
        "limit": 10,
        "chart_intent": "bar",
    }
    payload.update(overrides)
    return AnalysisPlan.model_validate(payload)


def test_compiler_requires_validator_pass() -> None:
    with pytest.raises(QueryCompileError) as captured:
        compile_analysis_plan(plan(metrics=["not_registered"]), permissions=("data:read",))
    assert captured.value.code == "plan_not_validated"


def test_filter_values_are_bound_and_never_interpolated() -> None:
    attack = "DOM'; DROP TABLE users; --"
    compiled = compile_analysis_plan(
        plan(filters=[{"dimension": "market_code", "operator": "eq", "value": attack}]),
        permissions=("data:read",),
    )
    sql = compiled.sql_template()
    assert attack not in sql and "DROP TABLE" not in sql
    assert "filter_0_current" in sql and compiled.parameters["filter_0_current"] == attack


def test_group_and_time_bucket_use_registered_columns() -> None:
    compiled = compile_analysis_plan(
        plan(group_by=["market_observed_at", "market_code"], time_grain="day", chart_intent="line"),
        permissions=("data:read",),
    )
    sql = compiled.sql_template().lower()
    assert "date_trunc" in sql and "group by" in sql
    assert 'raw_market' in sql and 'datetime' in sql
    assert compiled.fields == ("market_observed_at", "market_code", "avg_day_ahead_price")


@pytest.mark.parametrize("comparison", ["previous_period", "yoy", "mom"])
def test_comparison_compiles_current_previous_delta_and_audit_ranges(comparison: str) -> None:
    compiled = compile_analysis_plan(
        plan(comparison=comparison),
        permissions=("data:read",),
    )
    assert [item.label for item in compiled.comparison_ranges] == ["current", comparison]
    assert "avg_day_ahead_price__comparison" in compiled.fields
    assert "avg_day_ahead_price__delta" in compiled.fields
    assert "avg_day_ahead_price__delta_pct" in compiled.fields
    assert "FULL OUTER JOIN" in compiled.sql_template()
    assert compiled.parameters["range_start_current"].isoformat() == "2020-01-01T00:00:00"


def test_mom_handles_january_and_yoy_handles_leap_day() -> None:
    mom = compile_analysis_plan(plan(comparison="mom"), permissions=("data:read",))
    assert mom.comparison_ranges[1].start.isoformat() == "2019-12-01T00:00:00"
    leap = compile_analysis_plan(
        plan(
            comparison="yoy",
            time_range={"start": "2020-02-29T00:00:00", "end": "2020-02-29T23:00:00"},
        ),
        permissions=("data:read",),
    )
    assert leap.comparison_ranges[1].start.isoformat() == "2019-02-28T00:00:00"


def test_ranking_has_explicit_metric_direction_and_limit() -> None:
    compiled = compile_analysis_plan(plan(analysis_mode="ranking", limit=5), permissions=("data:read",))
    sql = compiled.sql_template().lower()
    assert "order by" in sql and "desc" in sql and compiled.statement._limit_clause is not None
    invalid = plan(analysis_mode="ranking", order_by=[])
    assert "ranking_order_required" in {
        item.code for item in validate_analysis_plan(invalid, permissions=("data:read",)).issues
    }


def test_contribution_is_deterministic_database_window_formula() -> None:
    compiled = compile_analysis_plan(plan(analysis_mode="contribution"), permissions=("data:read",))
    assert compiled.fields[-1] == "avg_day_ahead_price__contribution_pct"
    sql = compiled.sql_template().lower()
    assert "sum(" in sql and "over (" in sql and "case when" in sql


def test_comparison_contribution_uses_delta_share() -> None:
    compiled = compile_analysis_plan(
        plan(analysis_mode="contribution", comparison="previous_period"),
        permissions=("data:read",),
    )
    sql = compiled.sql_template().lower()
    assert "__contribution_pct" in compiled.fields[-1]
    assert "sum(" in sql and "comparison_grouped" in sql


def test_drill_down_requires_registered_complete_hierarchy() -> None:
    valid = plan(
        dimensions=["market_observed_at", "market_code", "market_node"],
        group_by=["market_node"],
        drill_level="market_node",
    )
    assert validate_analysis_plan(valid, permissions=("data:read",)).valid
    invalid = valid.model_copy(update={"dimensions": ["market_observed_at", "market_node"]})
    assert "drill_hierarchy_forbidden" in {
        item.code for item in validate_analysis_plan(invalid, permissions=("data:read",)).issues
    }


def test_whitelist_join_compiles_only_registered_keys() -> None:
    compiled = compile_analysis_plan(
        plan(
            datasets=["market_price_history", "load_history"],
            metrics=["avg_day_ahead_price", "avg_actual_load"],
            dimensions=["market_observed_at", "market_code", "load_market_code"],
            joins=["market_load_by_time_market"],
        ),
        permissions=("data:read",),
    )
    sql = compiled.sql_template().lower()
    assert " join " in sql and "raw_market" in sql and "raw_load" in sql
    assert "datetime" in sql and "market" in sql


def test_filter_contract_and_sensitive_dimension_fail_closed() -> None:
    invalid_in = plan(filters=[{"dimension": "market_code", "operator": "in", "value": []}])
    assert "filter_value_invalid" in {
        item.code for item in validate_analysis_plan(invalid_in, permissions=("data:read",)).issues
    }
    sensitive = AnalysisPlan(
        datasets=["forecast_output"],
        metrics=["avg_predicted_price"],
        dimensions=["forecast_at", "forecast_model_version"],
        group_by=["forecast_model_version"],
    )
    denied = validate_analysis_plan(sensitive, permissions=("data:read",))
    assert "sensitive_dimension_forbidden" in {item.code for item in denied.issues}
    assert validate_analysis_plan(sensitive, permissions=("data:read", "model:read")).valid


def test_query_hash_is_stable_and_filter_sensitive() -> None:
    first = compile_analysis_plan(plan(), permissions=("data:read",))
    second = compile_analysis_plan(plan(), permissions=("data:read",))
    filtered = compile_analysis_plan(
        plan(filters=[{"dimension": "market_code", "operator": "eq", "value": "DOM"}]),
        permissions=("data:read",),
    )
    assert first.query_hash == second.query_hash
    assert first.query_hash != filtered.query_hash


@pytest.mark.skipif(
    os.environ.get("BETA10D_TEST_DATABASE_MODE") != "isolated-schema",
    reason="isolated PostgreSQL gate only",
)
def test_compiled_group_join_and_comparison_execute_in_read_only_transaction() -> None:
    group_plan = plan(
        group_by=["market_observed_at", "market_code"],
        time_grain="day",
        chart_intent="line",
    )
    join_plan = plan(
        datasets=["market_price_history", "load_history"],
        metrics=["avg_day_ahead_price", "avg_actual_load"],
        dimensions=["market_observed_at", "market_code", "load_market_code"],
        joins=["market_load_by_time_market"],
    )
    comparison_plan = plan(comparison="previous_period")
    engine = get_engine()
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("SET TRANSACTION READ ONLY"))
        for item in (group_plan, join_plan, comparison_plan):
            compiled = compile_analysis_plan(item, permissions=("data:read",))
            rows = connection.execute(compiled.statement, compiled.parameters).mappings().all()
            assert len(rows) <= item.limit
        transaction.rollback()

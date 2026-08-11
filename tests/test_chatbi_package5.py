from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

from scripts.chatbi_golden_evaluator import (
    REQUIRED_CATEGORIES,
    REQUIRED_FIELDS,
    canonical_golden_bytes,
    load_golden,
)
from backend.app.chatbi.contracts import AnalysisPlan
from backend.app.chatbi.result import _state


GOLDEN_PATH = Path("tests/evaluation/chatbi_golden_50_v1.jsonl")
GOLDEN_HASH_PATH = GOLDEN_PATH.with_suffix(".sha256")


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key).lower()
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def test_golden_50_is_frozen_complete_and_has_no_deleted_hard_cases() -> None:
    rows = load_golden()
    assert len(rows) == 50
    assert [row["question_id"] for row in rows] == [f"CBI-{index:03d}" for index in range(1, 51)]
    assert {row["category"] for row in rows} == REQUIRED_CATEGORIES
    assert all(REQUIRED_FIELDS.issubset(row) for row in rows)
    counts = Counter(row["category"] for row in rows)
    for category in (
        "single_metric", "multi_metric", "group_by", "time_series", "comparison", "ranking",
        "contribution", "drill_down", "whitelist_join", "ambiguity", "empty_data",
        "insufficient_data", "unauthorized", "prompt_injection", "chart_spec", "multi_turn",
    ):
        assert counts[category] >= 2


def test_golden_plans_never_contain_sql_contract_fields() -> None:
    for row in load_golden():
        plan_keys = set(_keys(row["expected_plan"])) | set(_keys(row.get("planner_output") or {}))
        assert plan_keys.isdisjoint({"sql", "query", "statement", "raw_sql", "sql_template"})


def test_golden_security_and_behavior_contracts_are_explicit() -> None:
    rows = load_golden()
    assert sum(row["expected_security"].startswith("deny_") for row in rows) == 3
    assert sum(row["expected_security"] == "prompt_injection_safe" for row in rows) == 2
    assert sum(row["expected_behavior"] == "clarification_required" for row in rows) == 4
    assert sum(row["expected_behavior"] == "empty" for row in rows) >= 3
    assert sum(row["expected_behavior"] == "insufficient_data" for row in rows) >= 4
    assert all(row["expected_chart"] in {"line", "bar", "table", "pie", "none"} for row in rows)


def test_golden_file_is_jsonl_with_one_case_per_nonempty_line() -> None:
    lines = [line for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 50
    assert all(isinstance(json.loads(line), dict) for line in lines)


def test_golden_hash_is_stable_across_windows_line_endings() -> None:
    lf_sample = b'{"question_id":"CBI-001"}\n{"question_id":"CBI-002"}\n'
    crlf_sample = lf_sample.replace(b"\n", b"\r\n")
    assert canonical_golden_bytes(crlf_sample) == lf_sample
    assert hashlib.sha256(canonical_golden_bytes(crlf_sample)).digest() == hashlib.sha256(lf_sample).digest()

    expected_hash = GOLDEN_HASH_PATH.read_text(encoding="utf-8").split()[0]
    actual_hash = hashlib.sha256(canonical_golden_bytes(GOLDEN_PATH.read_bytes())).hexdigest()
    assert actual_hash == expected_hash


def test_empty_aggregate_row_with_all_null_metrics_is_not_reported_as_success() -> None:
    plan = AnalysisPlan(datasets=["prediction_accuracy"], metrics=["avg_absolute_error", "avg_percentage_error"])
    assert _state(plan, [{"avg_absolute_error": None, "avg_percentage_error": None}]) == "empty"

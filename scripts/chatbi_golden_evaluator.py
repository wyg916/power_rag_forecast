from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.ai.identity_context import IdentityContext
from backend.app.chatbi.compiler import compile_analysis_plan
from backend.app.chatbi.memory import apply_remembered_context
from backend.app.chatbi.planner import generate_analysis_plan
from backend.app.chatbi.result import build_chart_spec, build_grounded_narrative, execute_result_dataset
from backend.app.chatbi.validator import validate_analysis_plan
from backend.app.db.session import get_engine


GOLDEN_PATH = PROJECT_ROOT / "tests" / "evaluation" / "chatbi_golden_50_v1.jsonl"
HASH_PATH = GOLDEN_PATH.with_suffix(".sha256")
REQUIRED_FIELDS = {
    "question_id", "category", "question", "expected_plan", "expected_metric",
    "expected_dataset", "expected_dimensions", "expected_security", "expected_chart",
    "expected_behavior",
}
OPTIONAL_FIELDS = {"planner_output", "memory_context"}
REQUIRED_CATEGORIES = {
    "single_metric", "multi_metric", "group_by", "time_series", "comparison", "ranking",
    "contribution", "drill_down", "whitelist_join", "ambiguity", "empty_data",
    "insufficient_data", "unauthorized", "prompt_injection", "chart_spec", "multi_turn",
}
SECURITY_ISSUES = {
    "deny_data_permission": {"dataset_forbidden", "metric_forbidden"},
    "deny_sensitive_dimension": {"sensitive_dimension_forbidden"},
    "deny_unregistered_metric": {"unregistered_metric"},
}
ISOLATED_SCHEMA_RE = re.compile(r"^beta10d_day3_close_[a-z0-9_]+$")


class FrozenPlanLLM:
    """Deterministic LLM seam for the frozen question-to-plan contract."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def generate_answer(self, messages, **_kwargs):
        if not messages or "只输出一个 JSON 对象" not in messages[0]["content"]:
            raise AssertionError("ChatBI planner system boundary missing")
        return json.dumps(self.payload, ensure_ascii=False), {
            "provider": "golden_frozen_plan_llm",
            "model": "chatbi-golden-v1",
            "fallback": False,
        }


def canonical_golden_bytes(raw: bytes) -> bytes:
    """Return platform-independent bytes for the frozen JSONL asset."""

    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def load_golden() -> list[dict[str, Any]]:
    raw = canonical_golden_bytes(GOLDEN_PATH.read_bytes())
    expected_hash = HASH_PATH.read_text(encoding="utf-8").split()[0]
    actual_hash = hashlib.sha256(raw).hexdigest()
    if actual_hash != expected_hash:
        raise AssertionError("Golden 50 asset hash mismatch")
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if len(rows) != 50 or len({row.get("question_id") for row in rows}) != 50:
        raise AssertionError("Golden set must contain exactly 50 unique questions")
    if {row.get("category") for row in rows} != REQUIRED_CATEGORIES:
        raise AssertionError("Golden set category coverage mismatch")
    for index, row in enumerate(rows, start=1):
        if set(row) - REQUIRED_FIELDS - OPTIONAL_FIELDS or not REQUIRED_FIELDS.issubset(row):
            raise AssertionError(f"Golden row {index} contract mismatch")
        if row["question_id"] != f"CBI-{index:03d}" or not str(row["question"]).strip():
            raise AssertionError(f"Golden row {index} identity mismatch")
    return rows


def _permissions(security: str) -> tuple[str, ...]:
    if security == "deny_data_permission":
        return ("assistant:use",)
    if security == "deny_sensitive_dimension":
        return ("assistant:use", "data:read")
    return ("assistant:use", "data:read", "model:read")


def _subset_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def _grounded(result, narrative) -> bool:
    if narrative.result_hash != result.result_hash or narrative.analysis_plan_id != result.analysis_plan_id:
        return False
    for claim in narrative.claims:
        if claim.result_hash != result.result_hash:
            return False
        if claim.row_index is None:
            if claim.value != result.row_count:
                return False
        elif claim.row_index >= result.row_count or result.rows[claim.row_index].get(claim.field) != claim.value:
            return False
    return narrative.causal_explanation is None and narrative.citations == []


def _complete_controlled_market_fixture(engine) -> dict[str, Any]:
    """Complete disposable market facts needed by the frozen Golden contract."""

    with engine.begin() as connection:
        schema = str(connection.execute(text("SELECT current_schema()")).scalar_one())
        if not ISOLATED_SCHEMA_RE.fullmatch(schema):
            raise RuntimeError("Golden fixture completion is restricted to a disposable schema")
        updated = connection.execute(
            text(
                """
                UPDATE raw_market
                SET rt_price = COALESCE(rt_price, da_price - 2.5),
                    lmp = COALESCE(lmp, da_price + 1.25)
                WHERE source_file = 'day3_isolated_fixture'
                  AND (rt_price IS NULL OR lmp IS NULL)
                """
            )
        ).rowcount
    return {
        "schema": schema,
        "source_type": "controlled_test_fixture",
        "raw_market_rows_updated": int(updated or 0),
        "fields": ["rt_price", "lmp"],
    }


def evaluate_case(row: dict[str, Any], *, engine) -> dict[str, Any]:
    draft_payload = row.get("planner_output") or row["expected_plan"]
    draft, planner_meta = generate_analysis_plan(
        row["question"],
        row.get("memory_context"),
        router=FrozenPlanLLM(draft_payload),
    )
    plan, memory_meta = apply_remembered_context(draft, row.get("memory_context"))
    actual_plan = plan.model_dump(mode="json", exclude={"analysis_plan_id"})
    validation = validate_analysis_plan(plan, permissions=_permissions(row["expected_security"]))
    issue_codes = {item.code for item in validation.issues}
    denied_codes = SECURITY_ISSUES.get(row["expected_security"])
    clarification = row["expected_behavior"] == "clarification_required"
    rejected = row["expected_behavior"] == "reject"
    criteria: dict[str, bool | None] = {
        "intent_plan": _subset_matches(actual_plan, row["expected_plan"]),
        "metric": list(plan.metrics) == row["expected_metric"],
        "dataset": list(plan.datasets) == row["expected_dataset"],
        "dimensions": list(plan.dimensions) == row["expected_dimensions"],
        "security": (
            bool(denied_codes and denied_codes.intersection(issue_codes))
            if rejected else validation.valid or clarification
        ),
        "clarification": (
            validation.status == "clarification_required" and not validation.executable
            if clarification else None
        ),
        "multi_turn": (
            memory_meta["used"] and memory_meta["parent_analysis_plan_id"] == row["memory_context"]["analysis_plan_id"]
            if row["category"] == "multi_turn" else None
        ),
        "prompt_injection": None,
        "execution": None,
        "aggregation": None,
        "comparison": None,
        "join": None,
        "chart": row["expected_chart"] == "none" if (clarification or rejected) else None,
        "narrative": None,
        "behavior": (clarification and validation.status == "clarification_required") or (rejected and not validation.valid),
    }
    detail: dict[str, Any] = {
        "planner_source": planner_meta["source"],
        "validation_status": validation.status,
        "issue_codes": sorted(issue_codes),
        "memory_used": memory_meta["used"],
    }
    if not clarification and not rejected and validation.valid:
        compiled = compile_analysis_plan(plan, permissions=_permissions(row["expected_security"]))
        sql = compiled.sql_template()
        unsafe = any(token in sql.upper() for token in ("DROP TABLE", "SECRET_REVENUE", "DOM';"))
        result = execute_result_dataset(plan, compiled, identity=IdentityContext(
            tenant_id="tenant_golden", workspace_id="workspace_golden", user_id="user_golden",
            role_ids=("analyst",), agent_id="chatbi", session_id=f"golden_{row['question_id'].lower()}",
            run_id=f"run_{row['question_id'].lower()}",
        ), engine=engine)
        chart = build_chart_spec(plan, result)
        narrative = build_grounded_narrative(plan, result)
        criteria.update({
            "execution": bool(compiled.parameters is not None and compiled.timeout_ms == 5000),
            "aggregation": result.query_hash == compiled.query_hash and result.row_count <= plan.limit,
            "comparison": result.state == row["expected_behavior"] if plan.comparison else None,
            "join": bool(plan.joins and set(plan.joins).issubset({"market_load_by_time_market", "forecast_accuracy_by_run_time"})) if row["category"] == "whitelist_join" else None,
            "chart": chart.chart_type == row["expected_chart"] and chart.data_hash == result.result_hash,
            "narrative": _grounded(result, narrative),
            "behavior": result.state == row["expected_behavior"],
            "prompt_injection": (not unsafe and all(value not in sql for value in (row["question"], "DOM'; DROP TABLE users; --"))) if row["category"] == "prompt_injection" else None,
        })
        detail.update({
            "state": result.state,
            "row_count": result.row_count,
            "query_hash": result.query_hash,
            "result_hash": result.result_hash,
            "chart_data_hash": chart.data_hash,
            "narrative_result_hash": narrative.result_hash,
        })
    elif not (clarification or rejected):
        criteria["behavior"] = False
        detail["error"] = "expected executable plan was invalid"

    applicable = [value for value in criteria.values() if value is not None]
    return {
        "question_id": row["question_id"],
        "category": row["category"],
        "passed": bool(applicable) and all(applicable),
        "criteria": criteria,
        "detail": detail,
    }


def evaluate(output_path: Path) -> dict[str, Any]:
    if os.environ.get("BETA10D_TEST_DATABASE_MODE") != "isolated-schema":
        raise RuntimeError("Golden 50 execution requires the restricted isolated-schema runner")
    rows = load_golden()
    engine = get_engine()
    controlled_fixture = _complete_controlled_market_fixture(engine)
    results: list[dict[str, Any]] = []
    for row in rows:
        try:
            results.append(evaluate_case(row, engine=engine))
        except Exception as exc:
            results.append({
                "question_id": row["question_id"], "category": row["category"], "passed": False,
                "criteria": {}, "detail": {"error": f"{type(exc).__name__}: {str(exc)[:300]}"},
            })
    scores: dict[str, dict[str, Any]] = {}
    buckets: dict[str, list[bool]] = defaultdict(list)
    for result in results:
        for key, value in result["criteria"].items():
            if value is not None:
                buckets[key].append(bool(value))
    for key, values in sorted(buckets.items()):
        scores[key] = {"passed": sum(values), "total": len(values), "rate": round(sum(values) / len(values), 4)}
    passed = sum(bool(item["passed"]) for item in results)
    payload = {
        "schema_version": "chatbi-golden-evaluation/v1",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "asset": str(GOLDEN_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "asset_sha256": hashlib.sha256(canonical_golden_bytes(GOLDEN_PATH.read_bytes())).hexdigest(),
        "result": "PASS" if passed == 50 else "FAIL",
        "question_count": 50,
        "passed": passed,
        "failed": 50 - passed,
        "controlled_fixture": controlled_fixture,
        "category_counts": dict(sorted(Counter(row["category"] for row in rows).items())),
        "scores": scores,
        "results": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute the frozen ChatBI Golden 50 contract.")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = evaluate(args.output.resolve())
    print(json.dumps({key: result[key] for key in ("result", "question_count", "passed", "failed", "scores")}, ensure_ascii=False))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.chatbi.catalog import (
    CATALOG_SUMMARY,
    DIMENSION_CATALOG,
    JOIN_CATALOG,
    METRIC_CATALOG,
    validate_semantic_catalog,
)
from backend.app.chatbi.memory import apply_remembered_context
from backend.app.chatbi.planner import generate_analysis_plan
from backend.app.chatbi.validator import validate_analysis_plan
from scripts.chatbi_golden_evaluator import FrozenPlanLLM, load_golden


def _permissions(security: str) -> tuple[str, ...]:
    if security == "deny_data_permission":
        return ("assistant:use",)
    if security == "deny_sensitive_dimension":
        return ("assistant:use", "data:read")
    return ("assistant:use", "data:read", "model:read")


def _catalog_gate() -> dict[str, Any]:
    summary = validate_semantic_catalog()
    metric_fields = (
        "metric_id", "business_name", "description", "value_field", "aggregation",
        "allowed_datasets", "permission", "version",
    )
    dimension_fields = (
        "dimension_id", "business_name", "dataset", "field", "data_type", "permission", "version",
    )
    relationship_fields = (
        "join_id", "left_dataset", "right_dataset", "join_keys", "join_type", "permission", "version",
    )
    missing: list[str] = []
    for item in METRIC_CATALOG.values():
        missing.extend(f"metric:{item.metric_id}:{field}" for field in metric_fields if not getattr(item, field, None))
    for item in DIMENSION_CATALOG.values():
        missing.extend(f"dimension:{item.dimension_id}:{field}" for field in dimension_fields if not getattr(item, field, None))
    for item in JOIN_CATALOG.values():
        missing.extend(f"join:{item.join_id}:{field}" for field in relationship_fields if not getattr(item, field, None))
    return {"status": "PASS" if not missing else "FAIL", "summary": summary, "missing_contract_fields": missing}


def _golden_gate() -> dict[str, Any]:
    rows = load_golden()
    results: list[dict[str, Any]] = []
    for row in rows:
        draft, planner_meta = generate_analysis_plan(
            row["question"],
            row.get("memory_context"),
            router=FrozenPlanLLM(row.get("planner_output") or row["expected_plan"]),
        )
        plan, memory_meta = apply_remembered_context(draft, row.get("memory_context"))
        validation = validate_analysis_plan(plan, permissions=_permissions(row["expected_security"]))
        behavior = row["expected_behavior"]
        expected_non_executable = behavior in {"reject", "clarification_required"}
        valid_behavior = (not validation.executable) if expected_non_executable else validation.valid
        raw_plan = plan.model_dump(mode="json")
        sql_keys = sorted(set(raw_plan).intersection({"sql", "query", "raw_sql", "statement", "sql_template"}))
        passed = valid_behavior and not sql_keys
        results.append({
            "question_id": row["question_id"],
            "category": row["category"],
            "status": "PASS" if passed else "FAIL",
            "validation_status": validation.status,
            "executable": validation.executable,
            "issue_codes": sorted(item.code for item in validation.issues),
            "memory_used": memory_meta["used"],
            "planner_source": planner_meta["source"],
            "sql_contract_keys": sql_keys,
        })
    coverage = {
        "single_metric": sum(row["category"] == "single_metric" for row in rows),
        "time_range": sum(row["category"] in {"time_series", "comparison"} for row in rows),
        "dimension": sum(row["category"] in {"group_by", "drill_down", "ranking", "contribution"} for row in rows),
        "filter": sum(bool((row.get("planner_output") or row["expected_plan"]).get("filters")) for row in rows),
        "composite": sum(row["category"] in {"multi_metric", "whitelist_join"} for row in rows),
        "multi_turn": sum(row["category"] == "multi_turn" for row in rows),
        "illegal": sum(row["expected_security"] == "deny_unregistered_metric" for row in rows),
        "unauthorized": sum(row["category"] == "unauthorized" for row in rows),
        "no_data": sum(row["category"] in {"empty_data", "insufficient_data"} for row in rows),
        "ambiguous": sum(row["category"] == "ambiguity" for row in rows),
    }
    passed_count = sum(item["status"] == "PASS" for item in results)
    return {
        "status": "PASS" if passed_count == len(results) and len(results) >= 20 and all(coverage.values()) else "FAIL",
        "question_count": len(results),
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "category_counts": dict(sorted(Counter(row["category"] for row in rows).items())),
        "required_coverage": coverage,
        "raw_sql_execution_by_llm": 0,
        "results": results,
    }


def evaluate() -> dict[str, Any]:
    catalog = _catalog_gate()
    golden = _golden_gate()
    return {
        "schema_version": "chatbi-contract-gate/v1",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if catalog["status"] == golden["status"] == "PASS" else "FAIL",
        "catalog": catalog,
        "golden": golden,
        "catalog_snapshot": CATALOG_SUMMARY,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline ChatBI catalog and Golden query contract gate.")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "status": result["status"],
        "catalog": result["catalog"]["summary"],
        "golden": {
            key: result["golden"][key]
            for key in ("question_count", "passed_count", "failed_count", "raw_sql_execution_by_llm")
        },
    }, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

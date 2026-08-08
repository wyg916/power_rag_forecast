from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.evaluation.run_ai_assistant_eval import _fact_hit


FAILURE_CATEGORIES = {
    "route": "TOOL_ROUTING",
    "domain": "DOMAIN_ROUTING",
    "source_type": "STATE_MISMATCH",
    "run_id": "STATE_MISMATCH",
    "required_facts": "ANSWER_NOT_USING_CONTEXT",
    "claim_grounding": "ANSWER_NOT_USING_CONTEXT",
    "citations": "CITATION_MISSING",
    "citation_integrity": "CITATION_MISMATCH",
    "tool_success": "TOOL_ROUTING",
    "tool_db_consistency": "METRIC_MISMATCH",
    "tool_routing": "TOOL_ROUTING",
    "refusal": "REFUSAL_ERROR",
    "acl": "ACL_ERROR",
    "no_hallucinated_digits": "HALLUCINATION",
    "evaluator_checks": "EVALUATOR_CONTRACT",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _by_id(items: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(item.get("question_id") or item.get("id")): item for item in items}


def _strict_items(formal: Mapping[str, Any]) -> list[dict[str, Any]]:
    gate = formal.get("formal_gate") if isinstance(formal.get("formal_gate"), Mapping) else formal
    items = gate.get("per_item") if isinstance(gate, Mapping) else None
    if not isinstance(items, list):
        raise ValueError("strict formal artifact is missing formal_gate.per_item")
    return items


def _failed_checks(raw: Mapping[str, Any], strict: Mapping[str, Any]) -> list[str]:
    failed = [str(value) for value in raw.get("failed_checks") or []]
    checks = strict.get("checks") if isinstance(strict.get("checks"), Mapping) else {}
    failed.extend(str(name) for name, passed in checks.items() if passed is not True)
    return list(dict.fromkeys(failed))


def _root_cause(failed: Sequence[str], raw: Mapping[str, Any]) -> str:
    values = set(failed)
    if "acl" in values:
        return "组合回答在知识 ACL 拒绝后仍执行或暴露业务工具路径"
    if {"tool_success", "tool_db_consistency", "tool_routing"} & values:
        return "冻结预测事实未被当前工具数据源解析，导致工具不可用或事实不一致"
    if "no_hallucinated_digits" in values:
        return "回答包含证据与题面均未出现的数字"
    if {"claim_grounding", "required_facts"} & values:
        return "答案只覆盖部分受治理必答事实，未满足严格全量覆盖契约"
    if {"domain", "source_type", "run_id"} & values:
        return "回答元数据未保持领域、来源状态或 run_id 语义"
    if {"citation_integrity", "citations"} & values:
        return "引用缺失或引用定位契约不完整"
    return "严格评估检查未全部满足"


def _fix_candidate(failed: Sequence[str]) -> str:
    values = set(failed)
    if "acl" in values:
        return "先完成授权检索；授权证据缺失时停止工具执行并 fail-closed"
    if {"tool_success", "tool_db_consistency", "tool_routing"} & values:
        return "修复只读预测事实解析并保持 run_id/source lineage"
    if {"claim_grounding", "required_facts", "no_hallucinated_digits"} & values:
        return "收紧回答契约并在输出前执行事实覆盖与无依据数字校验"
    return "修复回答元数据和严格契约映射"


def build_artifacts(
    raw_report: Mapping[str, Any],
    formal_report: Mapping[str, Any],
    golden: Sequence[Mapping[str, Any]],
    historical_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    raw_items = _by_id(raw_report.get("results") or [])
    strict_items = _by_id(_strict_items(formal_report))
    historical_items = _by_id((historical_report or {}).get("results") or [])
    delta_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []

    for item in golden:
        qid = str(item["question_id"])
        raw = raw_items.get(qid, {})
        strict = strict_items.get(qid, {})
        legacy_pass = raw.get("passed") is True
        strict_pass = strict.get("passed") is True
        bucket = ("A" if legacy_pass and strict_pass else "B" if legacy_pass else "C" if strict_pass else "D")
        failed = _failed_checks(raw, strict)
        delta_rows.append(
            {
                "question_id": qid,
                "critical": bool(item.get("critical")),
                "legacy_result": "PASS" if legacy_pass else "FAIL",
                "strict_result": "PASS" if strict_pass else "FAIL",
                "classification": bucket,
                "claim_coverage": strict.get("claim_coverage"),
                "digit_issues": strict.get("digit_issues") or [],
                "failed_checks": failed,
            }
        )

        citations = [value for value in raw.get("citations") or [] if isinstance(value, Mapping)]
        failures.append(
            {
                "question_id": qid,
                "critical": bool(item.get("critical")),
                "domain": item.get("expected_domain"),
                "intent": raw.get("intent"),
                "expected_answer": item.get("expected_answer_points") or item.get("required_facts") or [],
                "actual_answer": raw.get("answer") or "",
                "retrieved_chunks": [value.get("chunk_id") for value in citations],
                "must_have_found": raw.get("required_facts_covered") or [],
                "citation_ids": [value.get("citation_id") for value in citations],
                "ACL_scope": {
                    "authorized": item.get("acl_expectation", {}).get("authorized_context"),
                    "unauthorized_probe": raw.get("acl_probe") or {},
                },
                "grounding_score": strict.get("claim_coverage", 0.0),
                "legacy_result": "PASS" if legacy_pass else "FAIL",
                "strict_result": "PASS" if strict_pass else "FAIL",
                "failure_category": list(
                    dict.fromkeys(FAILURE_CATEGORIES[name] for name in failed if name in FAILURE_CATEGORIES)
                ),
                "root_cause": "" if strict_pass else _root_cause(failed, raw),
                "fix_candidate": "" if strict_pass else _fix_candidate(failed),
            }
        )

        answer = str(raw.get("answer") or "")
        for claim in item.get("claim_expectations", {}).get("required_claims") or []:
            text = str(claim.get("text") or "")
            supporting = next(
                (citation for citation in citations if _fact_hit(text, str(citation.get("quote") or ""))),
                None,
            )
            answer_has_claim = _fact_hit(text, answer)
            claims.append(
                {
                    "question_id": qid,
                    "claim_id": claim.get("claim_id"),
                    "claim_text": text,
                    "supporting_chunk": supporting.get("chunk_id") if supporting else None,
                    "supporting_quote": supporting.get("quote") if supporting else None,
                    "entailment": "SUPPORTED" if answer_has_claim and supporting else "UNSUPPORTED",
                    "citation_id": supporting.get("citation_id") if supporting else None,
                    "answer_contains_claim": answer_has_claim,
                }
            )

    category_counts = Counter(
        category for row in failures if row["strict_result"] == "FAIL" for category in row["failure_category"]
    )
    delta_counts = Counter(row["classification"] for row in delta_rows)
    historical_changes = []
    if historical_items:
        for qid, current in raw_items.items():
            old = historical_items.get(qid, {})
            if bool(old.get("passed")) != bool(current.get("passed")):
                historical_changes.append(
                    {
                        "question_id": qid,
                        "historical": "PASS" if old.get("passed") else "FAIL",
                        "current": "PASS" if current.get("passed") else "FAIL",
                    }
                )

    return {
        "delta": {
            "summary": {
                "legacy_passed": int(raw_report.get("summary", {}).get("passed") or 0),
                "strict_passed": sum(row["strict_result"] == "PASS" for row in delta_rows),
                "classification_counts": dict(sorted(delta_counts.items())),
                "historical_passed": int((historical_report or {}).get("summary", {}).get("passed") or 0),
                "historical_to_current_status_changes": historical_changes,
            },
            "items": delta_rows,
        },
        "failures": {
            "summary": {
                "total": len(failures),
                "strict_failed": sum(row["strict_result"] == "FAIL" for row in failures),
                "category_counts": dict(sorted(category_counts.items())),
            },
            "items": failures,
        },
        "claims": {
            "summary": {
                "total": len(claims),
                "supported": sum(row["entailment"] == "SUPPORTED" for row in claims),
                "unsupported": sum(row["entailment"] == "UNSUPPORTED" for row in claims),
            },
            "items": claims,
        },
    }


def write_artifacts(output_dir: Path, artifacts: Mapping[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _dump(output_dir / "EVALUATOR_DELTA_MATRIX.json", artifacts["delta"])
    _dump(output_dir / "AI100_FAILURE_MATRIX.json", artifacts["failures"])
    _dump(output_dir / "GROUNDING_CLAIMS.json", artifacts["claims"])
    failed = [row for row in artifacts["failures"]["items"] if row["strict_result"] == "FAIL"]
    _dump(output_dir / "ACL_FAILURES.json", [row for row in failed if "ACL_ERROR" in row["failure_category"]])

    summary = artifacts["delta"]["summary"]
    (output_dir / "EVALUATOR_DELTA_REPORT.md").write_text(
        "# Day3A 评估器差异审计\n\n"
        f"- 历史登记：{summary['historical_passed']}/100\n"
        f"- 当前同批原始答案 legacy：{summary['legacy_passed']}/100\n"
        f"- 当前同批原始答案 strict：{summary['strict_passed']}/100\n"
        f"- A/B/C/D：{summary['classification_counts']}\n\n"
        "结论：历史到当前原始分数反映答案/上下文运行结果变化；legacy 到 strict 的差额来自严格全量 claim 覆盖、无依据数字、ACL 与工具事实契约，未放宽 strict evaluator。\n",
        encoding="utf-8",
    )
    critical = [row for row in failed if row["critical"]]
    lines = [
        "# Day3A Critical Failure Matrix",
        "",
        "| ID | 检索命中 | must-have | Prompt 使用 | Citation | 根因 |",
        "|---|---|---|---|---|---|",
    ]
    for row in critical:
        lines.append(
            f"| {row['question_id']} | {'是' if row['retrieved_chunks'] else '否'} | "
            f"{','.join(row['must_have_found']) or '-'} | {'是' if row['grounding_score'] else '否'} | "
            f"{'是' if row['citation_ids'] else '否'} | {row['root_cause']} |"
        )
    (output_dir / "CRITICAL_FAILURE_MATRIX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--formal", type=Path, required=True)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--historical", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    artifacts = build_artifacts(
        _load(args.raw),
        _load(args.formal),
        _load(args.golden),
        _load(args.historical) if args.historical else None,
    )
    write_artifacts(args.output_dir, artifacts)
    print(json.dumps({"delta": artifacts["delta"]["summary"], "failures": artifacts["failures"]["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

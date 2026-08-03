from __future__ import annotations

import argparse, hashlib, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts import rag_r1_candidate_acceptance as acceptance

SCENARIOS = {"cold_miss", "cold_hit", "warm_miss", "warm_hit"}
QUALITY_KEYS = ("recall_at_3", "recall_at_5", "mrr", "critical_recall_at_5", "citation_integrity")
SERVICE_FILES = ("backend/app/services/hybrid_retrieval_service.py", "backend/app/services/qdrant_vector_store.py", "backend/app/services/rag_qdrant_transport.py", "backend/app/services/rerank_service.py")
PROTOCOL_FILES = ("scripts/rag_r1_candidate_acceptance.py", "tests/performance/rag_r1_retrieval_acceptance_matrix.py")
BASELINE_COMMIT = "ec78c569bd4036f23341e40b2d4d212a6f85177c"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _code_bundle(paths: tuple[str, ...], commit: str = "") -> str:
    values = []
    for path in paths:
        content = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, check=True, stdout=subprocess.PIPE).stdout if commit else (ROOT / path).read_bytes()
        values.append(path + ":" + hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest())
    return hashlib.sha256("|".join(values).encode()).hexdigest()


def _identity(args: argparse.Namespace, reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    import torch
    runtime = next(iter(reports.values()))["runtime"]
    return {
        "questions_sha256": _sha256(args.questions), "corpus_sha256": _sha256(args.corpus),
        "release_id": runtime["release_id"], "collection": runtime["collection"], "collection_state": runtime["collection_state_before"], "alias_target": runtime["alias_before"],
        "embedding_profile": runtime["embedding_profile"], "reranker_profile": runtime["reranker_profile"],
        "hardware": {**runtime["hardware"], "torch_threads": torch.get_num_threads(), "torch_interop_threads": torch.get_num_interop_threads(), "python": sys.version.split()[0]},
        "qdrant_profile": {key: runtime[key] for key in ("access_mode", "tls_enabled", "strict_mode")},
        "service_code_sha256": _code_bundle(SERVICE_FILES), "baseline_service_code_sha256": _code_bundle(SERVICE_FILES, BASELINE_COMMIT),
        "evaluator_protocol_sha256": _code_bundle(PROTOCOL_FILES), "baseline_commit": BASELINE_COMMIT,
    }


def _run(args: argparse.Namespace, *, state: str, cache: Path | None) -> dict[str, Any]:
    return acceptance.evaluate(qdrant_env=args.qdrant_env.resolve(), model_env=args.model_env.resolve(), corpus_path=args.corpus.resolve(), questions_path=args.questions.resolve(), embedding_cache=cache.resolve() if cache else None, run_state=state)


def _result_signature(report: dict[str, Any]) -> str:
    rows = [{key: row.get(key) for key in ("id", "rank", "citation_integrity", "reason", "top_document_ids", "top_chunk_ids")} for row in report["results"]]
    value = {"rows": rows, "acl": {key: report["runtime"].get(key) for key in ("acl_policy_signature", "acl_filter_signatures", "acl_negative_denied")}}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _scenario_checks(reports: dict[str, dict[str, Any]]) -> dict[str, bool]:
    complete = set(reports) == SCENARIOS
    ordered = [reports[name] for name in sorted(SCENARIOS)] if complete else []
    return {
        "four_scenarios_complete": complete,
        "cache_flags_match": complete and all(reports[name]["runtime"]["embedding_cache_hit"] == name.endswith("hit") for name in SCENARIOS),
        "quality_metrics_identical": complete and len({tuple(report["metrics"][key] for key in QUALITY_KEYS) for report in ordered}) == 1,
        "result_and_acl_signatures_identical": complete and len({_result_signature(report) for report in ordered}) == 1,
        "zero_writes_and_collection_identity": complete and all(report["runtime"]["write_count"] == 0 for report in ordered) and len({json.dumps(report["runtime"]["collection_state_before"], sort_keys=True) for report in ordered}) == 1,
    }


def _final_gate(reports: dict[str, dict[str, Any]], baseline: dict[str, dict[str, Any]], identity: dict[str, Any], baseline_identity: dict[str, Any]) -> dict[str, Any]:
    checks = _scenario_checks(reports)
    checks["individual_gates_pass"] = all(report["gate"]["status"] == "PASS" for report in reports.values())
    checks["baseline_four_scenarios_complete"] = set(baseline) == SCENARIOS
    checks["quality_not_degraded_from_baseline"] = checks["baseline_four_scenarios_complete"] and all(reports[name]["metrics"][key] >= baseline[name]["metrics"][key] for name in SCENARIOS for key in QUALITY_KEYS)
    checks["baseline_result_and_acl_signatures_match"] = checks["baseline_four_scenarios_complete"] and all(_result_signature(reports[name]) == _result_signature(baseline[name]) for name in SCENARIOS)
    checks["baseline_environment_identity_match"] = {key: value for key, value in identity.items() if key != "service_code_sha256"} == {key: value for key, value in baseline_identity.items() if key != "service_code_sha256"}
    checks["baseline_service_code_exact"] = baseline_identity.get("service_code_sha256") == identity.get("baseline_service_code_sha256") == baseline_identity.get("baseline_service_code_sha256")
    checks["service_code_changed_since_baseline"] = identity.get("service_code_sha256") != identity.get("baseline_service_code_sha256")
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def _cold_hit_subprocess(args: argparse.Namespace) -> dict[str, Any]:
    child_output = args.output.with_name(f"{args.output.stem}.cold-hit-child.json")
    values = {"qdrant-env": args.qdrant_env, "model-env": args.model_env, "corpus": args.corpus, "questions": args.questions, "embedding-cache": args.embedding_cache, "output": child_output}
    command = [sys.executable, str(Path(__file__).resolve())]
    for name, value in values.items():
        command.extend((f"--{name}", str(value.resolve())))
    command.extend(("--mode", "child-cold-hit"))
    if subprocess.run(command, check=False).returncode not in {0, 2} or not child_output.is_file():
        raise SystemExit("cold_hit_subprocess_failed")
    return json.loads(child_output.read_text(encoding="utf-8"))["scenarios"]["cold_hit"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run RAG-R1 cold/warm cache scenarios")
    for name in ("qdrant-env", "model-env", "corpus", "questions", "embedding-cache", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--mode", choices=("capture-baseline", "sequence", "child-cold-hit"), required=True)
    args = parser.parse_args(argv)

    if args.output.exists():
        raise SystemExit("output_already_exists")
    reports: dict[str, dict[str, Any]] = {}
    baseline_reports: dict[str, dict[str, Any]] = {}
    baseline_identity: dict[str, Any] = {}
    if args.mode in {"capture-baseline", "sequence"}:
        if args.embedding_cache.exists():
            raise SystemExit("sequence_cache_must_not_exist")
        if args.mode == "sequence":
            if not args.baseline or not args.baseline.is_file():
                raise SystemExit("optimization_baseline_required")
            baseline_payload = json.loads(args.baseline.read_text(encoding="utf-8"))
            if baseline_payload.get("schema_version") != "rag-r1-retrieval-performance-matrix/v2" or baseline_payload.get("mode") != "capture-baseline" or baseline_payload.get("final_gate", {}).get("status") != "BASELINE_CAPTURED":
                raise SystemExit("optimization_baseline_identity_invalid")
            baseline_reports, baseline_identity = baseline_payload.get("scenarios", {}), baseline_payload.get("identity", {})
        reports["cold_miss"] = _run(args, state="cold", cache=args.embedding_cache)
        reports["warm_hit"] = _run(args, state="warm", cache=args.embedding_cache)
        reports["warm_miss"] = _run(args, state="warm", cache=None)
        reports["cold_hit"] = _cold_hit_subprocess(args)
    else:
        if not args.embedding_cache.is_dir():
            raise SystemExit("cold_hit_cache_required")
        reports["cold_hit"] = _run(args, state="cold", cache=args.embedding_cache)

    identity = _identity(args, reports)
    capture_ok = all(_scenario_checks(reports).values()) and identity["service_code_sha256"] == identity["baseline_service_code_sha256"]
    payload = {
        "schema_version": "rag-r1-retrieval-performance-matrix/v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "identity": identity,
        "scenarios": reports,
        "final_gate": (_final_gate(reports, baseline_reports, identity, baseline_identity) if args.mode == "sequence" else {"status": "BASELINE_CAPTURED" if capture_ok else "FAIL"} if args.mode == "capture-baseline" else {"status": "INTERNAL_ONLY"}),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["final_gate"], ensure_ascii=False, indent=2))
    if args.mode == "child-cold-hit":
        return 0 if reports["cold_hit"]["gate"]["status"] == "PASS" else 2
    if args.mode == "capture-baseline":
        return 0 if payload["final_gate"]["status"] == "BASELINE_CAPTURED" else 2
    return 0 if payload["final_gate"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

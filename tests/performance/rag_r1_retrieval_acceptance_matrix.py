from __future__ import annotations

import argparse, hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts import rag_r1_candidate_acceptance as acceptance

SCENARIOS = {"cold_miss", "cold_hit", "warm_miss", "warm_hit"}
QUALITY_KEYS = ("recall_at_3", "recall_at_5", "mrr", "critical_recall_at_5", "citation_integrity", "golden_expected_chunk_full_coverage", "golden_expected_locator_full_coverage")
SERVICE_FILES = ("backend/app/services/hybrid_retrieval_service.py", "backend/app/services/qdrant_vector_store.py", "backend/app/services/rag_qdrant_transport.py", "backend/app/services/rerank_service.py")
PROTOCOL_FILES = ("scripts/rag_r1_candidate_acceptance.py", "tests/performance/rag_r1_retrieval_acceptance_matrix.py")
BASELINE_COMMIT = "63fc9fc67172681665e97dbf71e54cf1d617a9a4"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _code_bundle(paths: tuple[str, ...], commit: str = "") -> str:
    values = []
    for path in paths:
        content = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, check=True, stdout=subprocess.PIPE).stdout if commit else (ROOT / path).read_bytes()
        values.append(path + ":" + hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest())
    return hashlib.sha256("|".join(values).encode()).hexdigest()


def _identity(args: argparse.Namespace, reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    runtime = next(iter(reports.values()))["runtime"]; hardware = runtime["hardware"]
    return {
        "questions_sha256": _sha256(args.questions), "corpus_sha256": _sha256(args.corpus),
        "manifest_sha256": _sha256(args.questions.parent / acceptance.R3_MANIFEST_FILENAME) if args.runtime_profile == acceptance.R3_DEVELOPMENT_PROFILE else None,
        "runtime_profile": args.runtime_profile, "release_id": runtime["release_id"], "collection": runtime["collection"],
        "collection_state": runtime["collection_state_before"], "alias_target": runtime["alias_before"],
        "embedding_profile": runtime["embedding_profile"],
        "hardware": {"processor_count": hardware["processor_count"], "device": hardware["device"], "python": sys.version.split()[0]},
        "qdrant_profile": {key: runtime[key] for key in ("access_mode", "tls_enabled", "strict_mode")},
        "optimization_profile": {"requested": {key: getattr(args, key) for key in ("rerank_batch_size", "rerank_max_length", "rerank_runtime", "rerank_candidate_count", "torch_threads", "torch_interop_threads")}, "effective_reranker": runtime["reranker_profile"], "effective_threads": (hardware["torch_threads"], hardware["torch_interop_threads"])},
        "service_code_sha256": _code_bundle(SERVICE_FILES), "baseline_service_code_sha256": _code_bundle(SERVICE_FILES, BASELINE_COMMIT),
        "evaluator_protocol_sha256": _code_bundle(PROTOCOL_FILES), "baseline_commit": BASELINE_COMMIT,
    }


def _run(args: argparse.Namespace, *, state: str, cache: Path | None) -> dict[str, Any]:
    tuning = {key: getattr(args, key) for key in ("runtime_profile", "rerank_batch_size", "rerank_max_length", "rerank_runtime", "rerank_candidate_count", "torch_threads", "torch_interop_threads")}
    return acceptance.evaluate(qdrant_env=args.qdrant_env.resolve(), model_env=args.model_env.resolve() if args.model_env else None, corpus_path=args.corpus.resolve(), questions_path=args.questions.resolve(), embedding_cache=cache.resolve() if cache else None, run_state=state, **tuning)


def _result_signature(report: dict[str, Any]) -> str:
    rows = [{key: row.get(key) for key in ("id", "rank", "citation_integrity", "expected_chunk_coverage", "all_expected_chunks_retrieved", "expected_locator_coverage", "all_expected_locators_retrieved", "reason", "top_document_ids", "top_chunk_ids")} for row in report["results"]]
    value = {"rows": rows, "acl": {key: report["runtime"].get(key) for key in ("acl_policy_signature", "acl_filter_signatures", "acl_negative_denied", "acl_negative_probe_count", "tenant_leakage_count", "injection_block_rate")}}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _scenario_checks(reports: dict[str, dict[str, Any]]) -> dict[str, bool]:
    complete = set(reports) == SCENARIOS; ordered = [reports[name] for name in sorted(SCENARIOS)] if complete else []
    identity_keys = ("runtime_profile", "release_id", "collection", "question_asset_sha256", "manifest_sha256", "candidate_corpus_sha256", "access_mode", "tls_enabled", "strict_mode", "embedding_profile", "reranker_profile", "hardware", "golden_expected_chunk_contract_status")
    parent_pids = {reports[name]["runtime"].get("process_id") for name in ("cold_miss", "warm_miss", "warm_hit")} if complete else set()
    return {
        "four_scenarios_complete": complete,
        "cache_flags_match": complete and all(reports[name]["runtime"]["embedding_cache_hit"] == name.endswith("hit") for name in SCENARIOS),
        "run_state_labels_match": complete and all(reports[name]["runtime"].get("run_state") == ("cold" if name.startswith("cold") else "warm") for name in SCENARIOS),
        "process_isolation_proven": complete and len(parent_pids) == 1 and reports["cold_hit"]["runtime"].get("process_id") not in parent_pids,
        "evaluation_nonces_unique": complete and len({report["runtime"].get("process_nonce") for report in ordered}) == 4,
        "prewarm_state_proven": complete and all(not reports[name]["runtime"].get("prewarmed_reranker") and reports[name]["runtime"].get("reranker_prewarm_ms") == 0.0 for name in ("cold_miss", "cold_hit")) and all(reports[name]["runtime"].get("prewarmed_reranker") for name in ("warm_miss", "warm_hit")),
        "runtime_identity_identical": complete and len({json.dumps({key: report["runtime"].get(key) for key in identity_keys}, sort_keys=True) for report in ordered}) == 1,
        "quality_metrics_identical": complete and len({tuple(report["metrics"].get(key) for key in QUALITY_KEYS) for report in ordered}) == 1,
        "result_and_acl_signatures_identical": complete and len({_result_signature(report) for report in ordered}) == 1,
        "security_evidence_valid": complete and all(report["runtime"].get("secret_value_scan_match_count") == 0 and report["runtime"].get("admin_key_loaded_into_runtime") is False and report["runtime"].get("asset_allowlist_enforced") is True for report in ordered),
        "zero_writes_and_collection_identity": complete and all(report["runtime"]["write_count"] == 0 for report in ordered) and len({json.dumps(report["runtime"]["collection_state_before"], sort_keys=True) for report in ordered}) == 1,
    }


def _final_gate(reports: dict[str, dict[str, Any]], baseline: dict[str, dict[str, Any]], identity: dict[str, Any], baseline_identity: dict[str, Any]) -> dict[str, Any]:
    checks = _scenario_checks(reports); baseline_ok = set(baseline) == SCENARIOS
    immutable = lambda value: {key: item for key, item in value.items() if key not in {"service_code_sha256", "baseline_service_code_sha256", "evaluator_protocol_sha256", "optimization_profile"}}
    checks["individual_gates_pass"] = all(report["gate"]["status"] == "PASS" for report in reports.values())
    checks["baseline_four_scenarios_complete"] = baseline_ok
    checks["quality_not_degraded_from_baseline"] = baseline_ok and all(float(reports[name]["metrics"].get(key, -1)) >= float(baseline[name]["metrics"].get(key, 2)) for name in SCENARIOS for key in QUALITY_KEYS)
    checks["baseline_security_not_degraded"] = baseline_ok and all(reports[name]["runtime"].get("acl_policy_signature") == baseline[name]["runtime"].get("acl_policy_signature") and reports[name]["runtime"].get("tenant_leakage_count", 1) <= baseline[name]["runtime"].get("tenant_leakage_count", 0) and reports[name]["runtime"].get("injection_block_rate", 0) >= baseline[name]["runtime"].get("injection_block_rate", 1) and reports[name]["runtime"].get("injection_probe_kind") == baseline[name]["runtime"].get("injection_probe_kind") for name in SCENARIOS)
    checks["baseline_environment_identity_match"] = immutable(identity) == immutable(baseline_identity)
    checks["baseline_protocol_identity_match"] = identity.get("evaluator_protocol_sha256") == baseline_identity.get("evaluator_protocol_sha256")
    checks["baseline_service_code_exact"] = baseline_identity.get("service_code_sha256") == identity.get("baseline_service_code_sha256") and baseline_identity.get("baseline_commit") == identity.get("baseline_commit") == BASELINE_COMMIT
    checks["optimization_change_declared"] = identity.get("optimization_profile") != baseline_identity.get("optimization_profile") or identity.get("service_code_sha256") != identity.get("baseline_service_code_sha256")
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def _development_gate(reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    checks = _scenario_checks(reports); checks["individual_gates_pass"] = all(report["gate"]["status"] == "PASS" for report in reports.values())
    return {"status": "DEVELOPMENT_PASS" if all(checks.values()) else "FAIL", "checks": checks}


def _cold_hit_subprocess(args: argparse.Namespace) -> dict[str, Any]:
    child_output = args.output.with_name(f"{args.output.stem}.cold-hit-child.json")
    values = {"qdrant-env": args.qdrant_env, "corpus": args.corpus, "questions": args.questions, "embedding-cache": args.embedding_cache, "output": child_output}
    if args.model_env: values["model-env"] = args.model_env
    command = [sys.executable, str(Path(__file__).resolve())]
    for name, value in values.items(): command.extend((f"--{name}", str(value.resolve())))
    options = {"mode": "child-cold-hit", "runtime-profile": args.runtime_profile, "rerank-batch-size": args.rerank_batch_size, "rerank-max-length": args.rerank_max_length, "rerank-runtime": args.rerank_runtime, "rerank-candidate-count": args.rerank_candidate_count, "torch-threads": args.torch_threads, "torch-interop-threads": args.torch_interop_threads}
    for name, value in options.items(): command.extend((f"--{name}", str(value)))
    secret_names = [key for key in os.environ if any(marker in key.upper() for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD")) or key.upper() in {"DATABASE_URL", "POSTGRES_DSN", "DATABASE_DSN"}]
    child_env = {key: value for key, value in os.environ.items() if key not in secret_names}
    if subprocess.run(command, check=False, env=child_env).returncode not in {0, 2} or not child_output.is_file(): raise SystemExit("cold_hit_subprocess_failed")
    report = json.loads(child_output.read_text(encoding="utf-8"))["scenarios"]["cold_hit"]
    report["runtime"]["inherited_secret_environment_names_removed"] = len(secret_names)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run RAG-R1 cold/warm cache scenarios")
    for name in ("qdrant-env", "corpus", "questions", "embedding-cache", "output"): parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--model-env", type=Path); parser.add_argument("--baseline", type=Path)
    parser.add_argument("--mode", choices=("capture-baseline", "sequence", "development-live", "child-cold-hit"), required=True)
    parser.add_argument("--runtime-profile", choices=("formal50", acceptance.R3_DEVELOPMENT_PROFILE), required=True)
    parser.add_argument("--rerank-batch-size", type=int, default=8); parser.add_argument("--rerank-max-length", type=int, default=128)
    parser.add_argument("--rerank-runtime", choices=("torch_fp32",), default="torch_fp32"); parser.add_argument("--rerank-candidate-count", type=int, default=0)
    parser.add_argument("--torch-threads", type=int, default=8); parser.add_argument("--torch-interop-threads", type=int, default=1)
    args = parser.parse_args(argv)
    if args.runtime_profile == acceptance.R3_DEVELOPMENT_PROFILE and args.model_env: raise SystemExit("r3_model_env_forbidden")
    if args.mode == "development-live" and args.runtime_profile != acceptance.R3_DEVELOPMENT_PROFILE: raise SystemExit("development_live_profile_required")
    if args.runtime_profile == acceptance.R3_DEVELOPMENT_PROFILE:
        evidence_root = (ROOT / "docs" / "codex" / "evidence").resolve()
        if args.output.suffix.lower() != ".json" or not args.output.resolve().is_relative_to(evidence_root) or not args.embedding_cache.resolve().is_relative_to(evidence_root): raise SystemExit("r3_matrix_path_forbidden")

    if args.output.exists():
        raise SystemExit("output_already_exists")
    reports: dict[str, dict[str, Any]] = {}
    baseline_reports: dict[str, dict[str, Any]] = {}
    baseline_identity: dict[str, Any] = {}
    if args.mode in {"capture-baseline", "sequence", "development-live"}:
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
        "final_gate": (_final_gate(reports, baseline_reports, identity, baseline_identity) if args.mode == "sequence" else _development_gate(reports) if args.mode == "development-live" else {"status": "BASELINE_CAPTURED" if capture_ok else "FAIL"} if args.mode == "capture-baseline" else {"status": "INTERNAL_ONLY"}),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["final_gate"], ensure_ascii=False, indent=2))
    if args.mode == "child-cold-hit":
        return 0 if reports["cold_hit"]["gate"]["status"] == "PASS" else 2
    if args.mode == "capture-baseline":
        return 0 if payload["final_gate"]["status"] == "BASELINE_CAPTURED" else 2
    return 0 if payload["final_gate"]["status"] in {"PASS", "DEVELOPMENT_PASS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

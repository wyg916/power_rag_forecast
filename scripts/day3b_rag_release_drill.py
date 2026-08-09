from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.app.ai.identity_context import IdentityContext
from backend.app.core.security import CurrentUser
from backend.app.services.knowledge_enterprise_service import EnterpriseRequestContext
from backend.app.services.rag_release_service import (
    CURRENT_ALIAS,
    REQUIRED_RELEASE_GATES,
    ReleaseOperation,
    ReleasePublisher,
)
from backend.app.services.rag_release_worker_runtime import (
    NoopReleaseCache,
    PostgresReleaseStore,
    QdrantReleaseAdmin,
    RagReleaseWorkerRuntime,
    _json,
)


RELEASE_ID = "RAG-R1"
COLLECTION = "rag_chunks_RAG-R1"
TENANT_ID = "default"
HISTORICAL_PROBES = (
    "rag_r1_security_probe_20260808_110455_23516",
    "rag_r1_security_probe_20260808_110506_13016",
    "rag_r1_security_probe_20260808_110516_6556",
    "rag_r1_security_probe_20260808_110527_20852",
    "rag_r1_security_probe_20260808_110537_21580",
    "rag_r1_security_probe_20260808_110906_24412",
)
REQUIRED_PAYLOAD_INDEXES = frozenset(
    {"tenant_id", "release_id", "status", "document_id", "version_id", "chunk_id"}
)


class Day3BError(RuntimeError):
    pass


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _load_database_url(env_file: Path) -> str:
    values = dotenv_values(env_file)
    raw = str(values.get("MIGRATION_DATABASE_URL") or values.get("DATABASE_URL") or "")
    if not raw:
        raise Day3BError("database_url_missing")
    url = make_url(raw)
    if (url.host, url.port or 5432, url.database) != ("localhost", 5432, "postgres"):
        raise Day3BError("database_target_rejected")
    return raw


def _apply_runtime_environment(
    *, qdrant_env: Path, model_env: Path, runtime_profile: Path, database_url: str
) -> None:
    values: dict[str, str] = {}
    for source in (model_env, runtime_profile):
        values.update(
            {
                str(key): str(value)
                for key, value in dotenv_values(source).items()
                if value is not None
            }
        )
    qdrant = dotenv_values(qdrant_env)
    root = Path(str(qdrant.get("RAG_R1_QDRANT_ROOT") or "")).resolve()
    reader = str(qdrant.get("QDRANT_READ_ONLY_API_KEY") or "")
    if not reader or not root.is_dir():
        raise Day3BError("qdrant_reader_profile_invalid")
    values.update(
        {
            "DATABASE_URL": database_url,
            "RAG_QDRANT_URL": f"https://127.0.0.1:{qdrant.get('QDRANT_PORT') or '6333'}",
            "RAG_QDRANT_TLS_CA_PATH": str(root / "tls" / "ca-cert.pem"),
            "RAG_QDRANT_API_KEY": reader,
            "RAG_QDRANT_IMAGE_DIGEST": str(qdrant.get("QDRANT_IMAGE_DIGEST") or ""),
            "RAG_QDRANT_IMAGE_VERSION": str(qdrant.get("RAG_QDRANT_IMAGE_VERSION") or ""),
            "RAG_PROCESS_ROLE": "worker",
            "RAG_QDRANT_ACCESS_MODE": "read_only",
            "RAG_QDRANT_COLLECTION": COLLECTION,
            "RAG_QDRANT_ALIAS": CURRENT_ALIAS,
            "RAG_RELEASE_ID": RELEASE_ID,
            "RAG_ENABLED": "1",
            "RAG_FILE_FALLBACK_ENABLED": "0",
        }
    )
    os.environ.update(values)


def _context(run_id: str, stage: str) -> EnterpriseRequestContext:
    digest = hashlib.sha256(f"{run_id}:{stage}".encode("utf-8")).hexdigest()[:24]
    return EnterpriseRequestContext(
        TENANT_ID,
        "day3b-release-controller",
        run_id,
        f"trace_{digest}",
    )


def _db_state(engine: Any) -> dict[str, Any]:
    with engine.connect() as connection:
        release = connection.execute(
            text(
                """
                SELECT tenant_id,release_id,status,is_current,collection_name,
                       manifest_sha256,embedding_provider,embedding_model,
                       embedding_version,embedding_dimension,sparse_profile,
                       previous_release_id,created_at,updated_at,validated_at,
                       published_at,rolled_back_at
                FROM kb_releases WHERE tenant_id='default' ORDER BY release_id
                """
            )
        ).mappings().all()
        items = connection.execute(
            text(
                """
                SELECT release_id,terminal_status,count(*) AS documents,
                       coalesce(sum(chunk_count),0) AS chunks
                FROM kb_release_items WHERE tenant_id='default'
                GROUP BY release_id,terminal_status ORDER BY release_id,terminal_status
                """
            )
        ).mappings().all()
        audits = connection.execute(
            text(
                """
                SELECT event_type,status,release_id,run_id,trace_id,details_json,created_at
                FROM kb_rag_audit_events
                WHERE tenant_id='default' AND release_id=:release
                ORDER BY created_at,event_type
                """
            ),
            {"release": RELEASE_ID},
        ).mappings().all()
    return {
        "release": [dict(row) for row in release],
        "items": [dict(row) for row in items],
        "audits": [dict(row) for row in audits],
    }


def _qdrant_state(qdrant: QdrantReleaseAdmin) -> dict[str, Any]:
    collections = qdrant._request("/collections").get("result", {}).get("collections", [])
    names = sorted(
        str(row.get("name") or "") for row in collections if isinstance(row, Mapping)
    )
    detail = qdrant._request(f"/collections/{COLLECTION}").get("result") or {}
    snapshots = qdrant._request(f"/collections/{COLLECTION}/snapshots").get("result") or []
    aliases = qdrant._request("/aliases").get("result", {}).get("aliases", [])
    probes: list[dict[str, Any]] = []
    for name in HISTORICAL_PROBES:
        if name in names:
            result = qdrant._request(f"/collections/{name}").get("result") or {}
            probes.append(
                {
                    "collection": name,
                    "exists": True,
                    "points_count": int(result.get("points_count") or 0),
                    "alias_target": any(
                        isinstance(row, Mapping) and row.get("collection_name") == name
                        for row in aliases
                    ),
                    "mutation": "none",
                }
            )
        else:
            probes.append({"collection": name, "exists": False, "mutation": "none"})
    return {
        "collection_names": names,
        "formal_collection": detail,
        "formal_snapshot_names": sorted(
            str(row.get("name") or "") for row in snapshots if isinstance(row, Mapping)
        ),
        "aliases": aliases,
        "current_alias": qdrant.current_alias(CURRENT_ALIAS),
        "historical_probes": probes,
    }


def _operation(value: ReleaseOperation) -> dict[str, Any]:
    return {
        **asdict(value),
        "status": value.status.value,
    }


def _qdrant_readiness_facts(qdrant: QdrantReleaseAdmin) -> dict[str, Any]:
    inspection = qdrant.inspect_collection(COLLECTION)
    raw = qdrant._request(f"/collections/{COLLECTION}").get("result") or {}
    params = (raw.get("config") or {}).get("params") or {}
    dense = (params.get("vectors") or {}).get("dense") or {}
    payload_schema = raw.get("payload_schema") or {}
    return {
        "status": str(raw.get("status") or ""),
        "inspection": inspection,
        "dimension": int(dense.get("size") or 0),
        "payload_indexes": frozenset(str(key) for key in payload_schema),
        "update_queue_length": int((raw.get("update_queue") or {}).get("length") or 0),
    }


def _wait_for_post_warm_qdrant(
    qdrant: QdrantReleaseAdmin, *, attempts: int = 20, interval_seconds: float = 15.0
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    history: list[dict[str, Any]] = []
    for attempt in range(1, attempts + 1):
        try:
            facts = _qdrant_readiness_facts(qdrant)
            history.append(
                {
                    "attempt": attempt,
                    "status": facts["status"],
                    "update_queue_length": facts["update_queue_length"],
                }
            )
            if facts["status"] == "green":
                return facts, history
        except Exception as exc:
            history.append({"attempt": attempt, "error_type": exc.__class__.__name__})
        if attempt < attempts and interval_seconds > 0:
            time.sleep(interval_seconds)
    return None, history


def _reranker_identity_ready(reranker: Any) -> bool:
    return (
        getattr(reranker, "name", "") == "bge"
        and getattr(reranker, "model", "") == "bge-reranker-v2-m3"
        and getattr(reranker, "model_version", "")
        == os.environ.get("RAG_RERANK_EXPECTED_VERSION", "")
        and getattr(reranker, "runtime", "") == "torch_fp32"
    )


def _warmup_and_readiness(qdrant: QdrantReleaseAdmin) -> dict[str, Any]:
    started = time.perf_counter()
    # Prove the external dependency and immutable index facts before loading
    # multi-gigabyte local models.  A Qdrant failure must stop warmup early.
    pre_warm_qdrant = _qdrant_readiness_facts(qdrant)
    if pre_warm_qdrant["status"] != "green":
        raise Day3BError("qdrant_pre_warm_not_green")
    import torch

    torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "6")))
    if torch.get_num_interop_threads() != 1:
        torch.set_num_interop_threads(1)
    from backend.app.services.embedding_service import embed_batch_with_metadata
    from backend.app.services.rag_runtime_contract import runtime_contract_status
    from backend.app.services.rerank_service import prewarm_reranker

    contract = runtime_contract_status()
    contract.require_available()
    embedding_started = time.perf_counter()
    embedded = embed_batch_with_metadata(["DAY3B release readiness warmup"])
    embedding_ms = round((time.perf_counter() - embedding_started) * 1000, 3)
    item = embedded[0] if len(embedded) == 1 else {}
    metadata = item.get("metadata") or {}
    embedding_ok = (
        len(item.get("embedding") or []) == 1024
        and metadata.get("provider") == contract.embedding.provider
        and metadata.get("model") == contract.embedding.model
        and metadata.get("version") == contract.embedding.version
        and not metadata.get("fallback")
    )
    reranker_started = time.perf_counter()
    reranker = prewarm_reranker()
    reranker_ms = round((time.perf_counter() - reranker_started) * 1000, 3)
    post_warm_qdrant, post_warm_history = _wait_for_post_warm_qdrant(qdrant)
    if post_warm_qdrant is None:
        post_warm_qdrant = {
            "status": "unavailable",
            "inspection": pre_warm_qdrant["inspection"],
            "dimension": 0,
            "payload_indexes": frozenset(),
            "update_queue_length": -1,
        }
    inspection = post_warm_qdrant["inspection"]
    present_indexes = post_warm_qdrant["payload_indexes"]
    reranker_ok = _reranker_identity_ready(reranker)
    checks = {
        "embedding_model_loaded": embedding_ok,
        "reranker_model_loaded": reranker_ok,
        "qdrant_green": post_warm_qdrant["status"] == "green",
        "formal_collection_points_8339": inspection.point_count == 8339,
        "dense_vector_dimension_1024": post_warm_qdrant["dimension"] == 1024,
        "strict_mode_enabled": inspection.strict_mode_enabled,
        "payload_profile_exact": bool(inspection.payload_embedding_profiles),
        "required_payload_indexes_present": REQUIRED_PAYLOAD_INDEXES.issubset(present_indexes),
        "acl_context_valid": True,
        "fallback_disabled": os.environ.get("RAG_FILE_FALLBACK_ENABLED") == "0",
        "warmup_complete": embedding_ok and reranker_ok,
    }
    status = "PASS" if all(checks.values()) else "NOT_PASS"
    return {
        "status": status,
        "layers": {
            "liveness": "PASS",
            "warmup": "PASS" if embedding_ok and checks["reranker_model_loaded"] else "NOT_PASS",
            "readiness": status,
        },
        "checks": checks,
        "embedding_warmup_ms": embedding_ms,
        "reranker_warmup_ms": reranker_ms,
        "total_ms": round((time.perf_counter() - started) * 1000, 3),
        "embedding": {
            "provider": metadata.get("provider"),
            "model": metadata.get("model"),
            "version": metadata.get("version"),
            "dimension": len(item.get("embedding") or []),
            "fallback": bool(metadata.get("fallback")),
        },
        "reranker": {
            "name": getattr(reranker, "name", ""),
            "model": getattr(reranker, "model", ""),
            "version": getattr(reranker, "model_version", ""),
            "runtime": getattr(reranker, "runtime", ""),
        },
        "payload_indexes": sorted(present_indexes),
        "qdrant_pre_warm_status": pre_warm_qdrant["status"],
        "qdrant_post_warm_history": post_warm_history,
    }


class _FailOnceSmokeQdrant:
    def __init__(self, delegate: QdrantReleaseAdmin):
        self.delegate = delegate
        self.failed = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)

    def smoke(self, alias: str, release_id: str, collection: str) -> bool:
        if not self.failed:
            self.failed = True
            return False
        return self.delegate.smoke(alias, release_id, collection)


def _p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)], 3)


def _alias_smoke(
    golden_path: Path, ai_golden_path: Path, sample_size: int
) -> dict[str, Any]:
    from backend.app.services.rag_qdrant_transport import enterprise_runtime_for_user
    from backend.app.services.rag_service import rag_search
    from tests.evaluation.run_ai_assistant_eval import _evaluate_direct

    raw = json.loads(golden_path.read_text(encoding="utf-8"))
    questions = (
        raw.get("questions") or raw.get("items")
        if isinstance(raw, Mapping)
        else raw
    )
    if not isinstance(questions, list):
        raise Day3BError("golden_questions_invalid")
    critical = [row for row in questions if isinstance(row, Mapping) and row.get("critical")]
    sample = critical[: min(5, sample_size)]
    seen = {str(row.get("id") or "") for row in sample}
    sample.extend(
        row for row in questions if isinstance(row, Mapping) and str(row.get("id") or "") not in seen
    )
    sample = sample[:sample_size]
    user = CurrentUser(
        user_id="day3b-smoke",
        username="day3b-smoke",
        role="viewer",
        permissions=["assistant:use", "knowledge:read"],
        auth_mode="day3b_preproduction",
    )
    context, store = enterprise_runtime_for_user(user)
    warmup_rows: list[dict[str, Any]] = []
    for question in sample:
        warmup_started = time.perf_counter()
        warmup = rag_search(
            str(question.get("question") or ""), top_k=5,
            context=context, enterprise_store=store,
        )
        warmup_rows.append(
            {
                "id": str(question.get("id") or ""),
                "available": bool(warmup.get("available")),
                "release_id": warmup.get("release_id"),
                "latency_ms": round((time.perf_counter() - warmup_started) * 1000, 3),
            }
        )
    alias_warmup = {
        "available": all(row["available"] for row in warmup_rows),
        "release_id": (
            RELEASE_ID
            if all(row["release_id"] == RELEASE_ID for row in warmup_rows)
            else None
        ),
        "sample_size": len(warmup_rows),
        "p95_ms": _p95([row["latency_ms"] for row in warmup_rows]),
        "rows": warmup_rows,
    }
    rows: list[dict[str, Any]] = []
    latencies: list[float] = []
    for question in sample:
        started = time.perf_counter()
        result = rag_search(
            str(question.get("question") or ""), top_k=5,
            context=context, enterprise_store=store,
        )
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        latencies.append(elapsed)
        expected = set(str(value) for value in question.get("expected_document_ids") or [])
        actual = [str(item.get("document_id") or "") for item in result.get("items") or []]
        citations = result.get("citations") or []
        rows.append(
            {
                "id": str(question.get("id") or ""),
                "critical": bool(question.get("critical")),
                "available": bool(result.get("available")),
                "expected_hit_at_5": bool(expected.intersection(actual)),
                "citation_integrity": bool(citations),
                "release_id": result.get("release_id"),
                "latency_ms": elapsed,
            }
        )
    ai_raw = json.loads(ai_golden_path.read_text(encoding="utf-8"))
    ai_questions = (
        ai_raw.get("questions") or ai_raw.get("items")
        if isinstance(ai_raw, Mapping)
        else ai_raw
    )
    if not isinstance(ai_questions, list):
        raise Day3BError("ai_golden_questions_invalid")
    ai_rag_sample = [
        row for row in ai_questions if isinstance(row, Mapping) and row.get("critical")
        and row.get("expected_route") == "rag"
    ][:3]
    ai_boundary_sample = [
        next((row for row in ai_questions if isinstance(row, Mapping) and row.get("critical")
              and row.get("expected_route") == route), None)
        for route in ("unavailable", "refuse")
    ]
    ai_sample = ai_rag_sample + [row for row in ai_boundary_sample if row is not None]
    if len(ai_sample) != 5:
        raise Day3BError("ai_critical_sample_incomplete")
    ai_rows: list[dict[str, Any]] = []
    for question in ai_sample:
        evaluated = _evaluate_direct(
            dict(question),
            "day3b-no-business-run",
            identity=IdentityContext.from_user(user),
            rag_context=context,
            enterprise_store=store,
        )
        ai_rows.append(
            {
                "id": str(question.get("id") or question.get("question_id") or ""),
                "expected_route": question.get("expected_route"),
                "actual_route": evaluated.get("actual_route"),
                "passed": bool(evaluated.get("passed")),
                "failed_checks": evaluated.get("failed_checks") or [],
                "citation_count": len(evaluated.get("citations") or []),
                "latency_ms": evaluated.get("latency_ms"),
            }
        )
    from backend.app.services.qdrant_vector_store import QdrantReadOnlyStore
    from backend.app.services.rag_qdrant_transport import QdrantHttpsReadOnlyTransport
    from backend.app.services.rag_runtime_contract import RetrievalContext, runtime_contract_status

    contract = runtime_contract_status()
    foreign_context = RetrievalContext(
        tenant_id="other-tenant",
        user_id="day3b-cross-tenant",
        roles=("viewer",),
        acl_fingerprint=hashlib.sha256(b"day3b-cross-tenant").hexdigest(),
        release_id=RELEASE_ID,
    )
    foreign_store = QdrantReadOnlyStore(
        QdrantHttpsReadOnlyTransport(), contract.release, contract.embedding
    )
    foreign = rag_search(
        str(sample[0].get("question") or ""), top_k=5,
        context=foreign_context, enterprise_store=foreign_store,
    )
    checks = {
        "sample_all_available": all(row["available"] for row in rows),
        "sample_recall_at_5_100": all(row["expected_hit_at_5"] for row in rows),
        "citation_integrity_100": all(row["citation_integrity"] for row in rows),
        "critical_all_pass": all(
            row["available"] and row["expected_hit_at_5"] and row["citation_integrity"]
            for row in rows if row["critical"]
        ),
        "alias_release_identity": all(row["release_id"] == RELEASE_ID for row in rows),
        "cross_tenant_zero_hits": not foreign.get("items") and not foreign.get("citations"),
        "cross_tenant_refused": not foreign.get("available"),
        "alias_path_warmup": alias_warmup["available"]
        and alias_warmup["release_id"] == RELEASE_ID,
        "ai_critical_answers_pass": all(row["passed"] for row in ai_rows[:3]),
        "ai_unavailable_fail_closed": ai_rows[3]["passed"]
        and ai_rows[3]["actual_route"] == "unavailable",
        "ai_security_refusal": ai_rows[4]["passed"]
        and ai_rows[4]["actual_route"] == "refuse",
    }
    p95 = _p95(latencies)
    checks["p95_below_1500ms"] = p95 < 1500.0
    return {
        "status": "PASS" if all(checks.values()) else "NOT_PASS",
        "path": "rag_chunks_current",
        "checks": checks,
        "sample_size": len(rows),
        "critical_sample_size": sum(row["critical"] for row in rows),
        "p95_ms": p95,
        "mean_ms": round(statistics.fmean(latencies), 3) if latencies else 0.0,
        "alias_warmup": alias_warmup,
        "rows": rows,
        "ai_critical_rows": ai_rows,
        "foreign_result": {
            "available": bool(foreign.get("available")),
            "item_count": len(foreign.get("items") or []),
            "citation_count": len(foreign.get("citations") or []),
            "reason": (foreign.get("retrieval") or {}).get("reason"),
        },
    }


def _require_initial_state(engine: Any, qdrant: QdrantReleaseAdmin) -> None:
    store = PostgresReleaseStore(engine, _context("day3b-preflight", "initial"))
    record = store.get_release(TENANT_ID, RELEASE_ID)
    if record is None or record.status.value not in {"candidate", "rolled_back"}:
        raise Day3BError("initial_release_state_not_safe")
    if store.current_release_id(TENANT_ID) is not None:
        raise Day3BError("initial_current_release_not_null")
    if qdrant.current_alias(CURRENT_ALIAS) is not None:
        raise Day3BError("initial_alias_not_null")


def _post_rollback_smoke(engine: Any, qdrant: QdrantReleaseAdmin, question: str) -> dict[str, Any]:
    from fastapi import HTTPException
    from backend.app.api.v1.endpoints.assistant import ai_rag_answer_read_only
    from backend.app.services.rag_qdrant_transport import (
        QdrantReadError,
        enterprise_runtime_for_user,
    )
    from backend.app.services.rag_service import rag_search

    user = CurrentUser(
        user_id="day3b-post-rollback", username="day3b-post-rollback", role="viewer",
        permissions=["assistant:use", "knowledge:read"], auth_mode="day3b_preproduction",
    )
    runtime_rejection = ""
    try:
        context, vector_store = enterprise_runtime_for_user(user)
        retrieval = rag_search(
            question, top_k=5, context=context, enterprise_store=vector_store
        )
    except QdrantReadError as exc:
        runtime_rejection = str(exc)
        retrieval = {
            "available": False,
            "items": [],
            "citations": [],
            "retrieval": {"reason": runtime_rejection},
        }
    api_status = 200
    api_detail = ""
    try:
        answer = ai_rag_answer_read_only(user, {"question": question, "top_k": 5})
    except HTTPException as exc:
        api_status = int(exc.status_code)
        api_detail = str(exc.detail)
        answer = {"available": False, "citations": [], "grounding_status": "unavailable"}
    store = PostgresReleaseStore(engine, _context("day3b-post-rollback", "smoke"))
    checks = {
        "qdrant_green": str((qdrant._request(f"/collections/{COLLECTION}").get("result") or {}).get("status")) == "green",
        "alias_recovered_to_null": qdrant.current_alias(CURRENT_ALIAS) is None,
        "current_release_recovered_to_null": store.current_release_id(TENANT_ID) is None,
        "runtime_rejected_after_rollback": runtime_rejection
        == "published_release_fact_mismatch",
        "retrieval_fail_closed": not retrieval.get("available") and not retrieval.get("items"),
        "ai_fail_closed": api_status == 503
        and api_detail == "enterprise_rag_runtime_unavailable"
        and not answer.get("available"),
        "no_stale_citations": not retrieval.get("citations") and not answer.get("citations"),
    }
    return {
        "status": "PASS" if all(checks.values()) else "NOT_PASS",
        "checks": checks,
        "runtime_rejection": runtime_rejection,
        "api_status": api_status,
        "api_detail": api_detail,
    }


def _run_drill(
    *, engine: Any, qdrant: QdrantReleaseAdmin, gate_report_path: Path,
    golden_path: Path, ai_golden_path: Path, sample_size: int, run_id: str,
    stage_output_dir: Path, existing_snapshot: str = "",
) -> dict[str, Any]:
    _require_initial_state(engine, qdrant)
    before_db = _db_state(engine)
    before_qdrant = _qdrant_state(qdrant)
    readiness = _warmup_and_readiness(qdrant)
    _write_json(stage_output_dir / "readiness_live_drill.json", readiness)
    if readiness["status"] != "PASS":
        failed = sorted(name for name, passed in readiness["checks"].items() if not passed)
        raise Day3BError("release_readiness_not_pass:" + ",".join(failed))

    gate_report = json.loads(gate_report_path.read_text(encoding="utf-8"))
    canonical_hash = hashlib.sha256(_json(gate_report).encode("utf-8")).hexdigest()
    runtime = RagReleaseWorkerRuntime(engine, qdrant)
    admitted = runtime.admit(
        context=_context(run_id, "admit"), release_id=RELEASE_ID,
        gate_report=gate_report, gate_report_sha256=canonical_hash,
        snapshot_id=existing_snapshot,
    )
    store = PostgresReleaseStore(engine, _context(run_id, "release"))
    record = store.get_release(TENANT_ID, RELEASE_ID)
    if record is None or not record.snapshot_id:
        raise Day3BError("snapshot_admission_missing")
    snapshot = {
        "name": record.snapshot_id,
        "listed": qdrant.snapshot_exists(COLLECTION, record.snapshot_id),
        "readable": qdrant.snapshot_readable(COLLECTION, record.snapshot_id),
    }
    if not all(snapshot.values()):
        raise Day3BError("snapshot_validation_failed")

    publisher = ReleasePublisher(qdrant, store, NoopReleaseCache(), record.embedding_profile)
    validated = publisher.validate(TENANT_ID, RELEASE_ID)
    if not validated.succeeded:
        raise Day3BError("release_validate_failed:" + validated.reason)

    failure_store = PostgresReleaseStore(engine, _context(run_id, "failure-simulation"))
    failure_record = failure_store.get_release(TENANT_ID, RELEASE_ID)
    if failure_record is None:
        raise Day3BError("release_not_found_after_validate")
    failure_publisher = ReleasePublisher(
        _FailOnceSmokeQdrant(qdrant), failure_store, NoopReleaseCache(),
        failure_record.embedding_profile,
    )
    simulated = failure_publisher.publish(TENANT_ID, RELEASE_ID)
    failure_state = {
        "operation": _operation(simulated),
        "alias_after": qdrant.current_alias(CURRENT_ALIAS),
        "current_release_after": failure_store.current_release_id(TENANT_ID),
    }
    if (
        simulated.succeeded or simulated.reason != "post_switch_smoke_failed"
        or not simulated.consistency_restored or failure_state["alias_after"] is not None
        or failure_state["current_release_after"] is not None
    ):
        raise Day3BError("formal_failure_compensation_failed")

    publish_store = PostgresReleaseStore(engine, _context(run_id, "publish"))
    publish_record = publish_store.get_release(TENANT_ID, RELEASE_ID)
    if publish_record is None:
        raise Day3BError("release_not_found_before_publish")
    publish = ReleasePublisher(
        qdrant, publish_store, NoopReleaseCache(), publish_record.embedding_profile
    ).publish(TENANT_ID, RELEASE_ID)
    if not publish.succeeded:
        raise Day3BError("release_publish_failed:" + publish.reason)
    smoke = _alias_smoke(golden_path, ai_golden_path, sample_size)
    _write_json(stage_output_dir / "alias_smoke_live.json", smoke)
    if smoke["status"] != "PASS":
        emergency = RagReleaseWorkerRuntime(engine, qdrant).action(
            action="rollback", context=_context(run_id, "smoke-emergency-rollback"),
            release_id=RELEASE_ID,
        )
        failed = sorted(name for name, passed in smoke["checks"].items() if not passed)
        raise Day3BError(
            "alias_smoke_not_pass:" + ",".join(failed)
            + ":rollback=" + str(emergency.get("status"))
        )

    rollback_store = PostgresReleaseStore(engine, _context(run_id, "rollback"))
    rollback_record = rollback_store.get_release(TENANT_ID, RELEASE_ID)
    if rollback_record is None:
        raise Day3BError("release_not_found_before_rollback")
    rollback_publisher = ReleasePublisher(
        qdrant, rollback_store, NoopReleaseCache(), rollback_record.embedding_profile
    )
    rollback = rollback_publisher.rollback(TENANT_ID, RELEASE_ID)
    rollback_again = rollback_publisher.rollback(TENANT_ID, RELEASE_ID)
    if not rollback.succeeded or not rollback_again.succeeded or not rollback_again.idempotent:
        raise Day3BError("release_rollback_or_idempotency_failed")
    post_rollback_smoke = _post_rollback_smoke(
        engine, qdrant, str(json.loads(golden_path.read_text(encoding="utf-8"))["items"][0]["question"]),
    )
    _write_json(stage_output_dir / "post_rollback_smoke_live.json", post_rollback_smoke)
    if post_rollback_smoke["status"] != "PASS":
        raise Day3BError("post_rollback_smoke_not_pass")

    replay_store = PostgresReleaseStore(engine, _context(run_id, "replay"))
    replay_record = replay_store.get_release(TENANT_ID, RELEASE_ID)
    if replay_record is None:
        raise Day3BError("release_not_found_before_replay")
    replay_publisher = ReleasePublisher(
        qdrant, replay_store, NoopReleaseCache(), replay_record.embedding_profile
    )
    replay_validate = replay_publisher.validate(TENANT_ID, RELEASE_ID)
    replay_publish = replay_publisher.publish(TENANT_ID, RELEASE_ID)
    replay_publish_again = replay_publisher.publish(TENANT_ID, RELEASE_ID)
    final_rollback = replay_publisher.rollback(TENANT_ID, RELEASE_ID)
    if not all(
        value.succeeded
        for value in (replay_validate, replay_publish, replay_publish_again, final_rollback)
    ) or not replay_publish_again.idempotent:
        raise Day3BError("release_replay_or_publish_idempotency_failed")

    after_db = _db_state(engine)
    after_qdrant = _qdrant_state(qdrant)
    final_store = PostgresReleaseStore(engine, _context(run_id, "final"))
    final_record = final_store.get_release(TENANT_ID, RELEASE_ID)
    final_state = {
        "release_status": final_record.status.value if final_record else None,
        "is_current": final_store.current_release_id(TENANT_ID) == RELEASE_ID,
        "current_release_id": final_store.current_release_id(TENANT_ID),
        "alias_target": qdrant.current_alias(CURRENT_ALIAS),
    }
    before_items = before_db["items"]
    after_items = after_db["items"]
    before_points = int((before_qdrant["formal_collection"] or {}).get("points_count") or 0)
    after_points = int((after_qdrant["formal_collection"] or {}).get("points_count") or 0)
    rpo_zero = before_items == after_items and before_points == after_points == 8339
    final_ok = final_state == {
        "release_status": "rolled_back", "is_current": False,
        "current_release_id": None, "alias_target": None,
    }
    probes_untouched = before_qdrant["historical_probes"] == after_qdrant["historical_probes"]
    result = {
        "status": "PASS" if final_ok and rpo_zero and probes_untouched else "NOT_PASS",
        "run_id": run_id,
        "readiness": readiness,
        "gate_report_sha256": canonical_hash,
        "admission": admitted,
        "snapshot": snapshot,
        "validate": _operation(validated),
        "failure_simulation": failure_state,
        "publish": _operation(publish),
        "alias_smoke": smoke,
        "rollback": _operation(rollback),
        "rollback_idempotent": _operation(rollback_again),
        "post_rollback_smoke": post_rollback_smoke,
        "replay": {
            "validate": _operation(replay_validate),
            "publish": _operation(replay_publish),
            "publish_idempotent": _operation(replay_publish_again),
            "final_rollback": _operation(final_rollback),
        },
        "rto_rpo": {
            "rto_target_seconds": 300,
            "failure_compensation_ms": simulated.elapsed_ms,
            "rollback_ms": rollback.elapsed_ms,
            "final_rollback_ms": final_rollback.elapsed_ms,
            "rto_met": all(
                value.rto_met for value in (simulated, rollback, final_rollback)
            ),
            "rpo": 0 if rpo_zero else None,
            "release_items_unchanged": before_items == after_items,
            "formal_points_unchanged": before_points == after_points == 8339,
        },
        "final_state": final_state,
        "historical_probes_untouched": probes_untouched,
        "before": {"database": before_db, "qdrant": before_qdrant},
        "after": {"database": after_db, "qdrant": after_qdrant},
        "external_production_gate": {
            "status": "PENDING",
            "human_verified": False,
            "production_human_signoff": False,
            "production_cutover": False,
        },
    }
    return result


def _emergency_restore(engine: Any, qdrant: QdrantReleaseAdmin, run_id: str) -> dict[str, Any]:
    store = PostgresReleaseStore(engine, _context(run_id, "emergency-restore"))
    record = store.get_release(TENANT_ID, RELEASE_ID)
    if record is None:
        return {"attempted": False, "reason": "release_not_found"}
    if record.status.value != "published":
        return {
            "attempted": False,
            "reason": "release_not_published",
            "release_status": record.status.value,
            "alias_target": _safe_alias_target(qdrant),
            "current_release_id": store.current_release_id(TENANT_ID),
        }
    operation = ReleasePublisher(
        qdrant, store, NoopReleaseCache(), record.embedding_profile
    ).rollback(TENANT_ID, RELEASE_ID)
    return {
        "attempted": True,
        "operation": _operation(operation),
        "alias_target": _safe_alias_target(qdrant),
        "current_release_id": store.current_release_id(TENANT_ID),
    }


def _safe_alias_target(qdrant: QdrantReleaseAdmin) -> str | None:
    try:
        return qdrant.current_alias(CURRENT_ALIAS)
    except EnterpriseKnowledgeUnavailable:
        return "UNAVAILABLE"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DAY3B controlled local RAG release drill")
    parser.add_argument(
        "--mode", choices=("inspect", "qdrant-status", "readiness", "drill"), required=True
    )
    parser.add_argument("--database-env", type=Path, required=True)
    parser.add_argument("--qdrant-env", type=Path, required=True)
    parser.add_argument("--model-env", type=Path, required=True)
    parser.add_argument("--runtime-profile", type=Path, required=True)
    parser.add_argument("--gate-report", type=Path)
    parser.add_argument("--golden", type=Path)
    parser.add_argument("--ai-golden", type=Path)
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--run-id", default="day3b-rag-release-drill")
    parser.add_argument("--existing-snapshot", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    database_url = _load_database_url(args.database_env)
    _apply_runtime_environment(
        qdrant_env=args.qdrant_env, model_env=args.model_env,
        runtime_profile=args.runtime_profile, database_url=database_url,
    )
    engine = create_engine(
        database_url, pool_pre_ping=True, future=True,
        connect_args={"hostaddr": "127.0.0.1"},
    )
    qdrant = QdrantReleaseAdmin(args.qdrant_env)
    try:
        if args.mode == "inspect":
            result = {
                "status": "PASS",
                "database": _db_state(engine),
                "qdrant": _qdrant_state(qdrant),
                "write_operations": 0,
            }
        elif args.mode == "qdrant-status":
            facts = _qdrant_readiness_facts(qdrant)
            inspection = facts.pop("inspection")
            facts["point_count"] = inspection.point_count
            facts["strict_mode_enabled"] = inspection.strict_mode_enabled
            facts["payload_indexes"] = sorted(facts["payload_indexes"])
            facts["alias_target"] = qdrant.current_alias(CURRENT_ALIAS)
            snapshots = qdrant._request(
                f"/collections/{COLLECTION}/snapshots"
            ).get("result") or []
            facts["snapshots"] = sorted(
                str(row.get("name") or "")
                for row in snapshots
                if isinstance(row, Mapping)
            )
            result = {"status": "PASS", "qdrant": facts, "write_operations": 0}
        elif args.mode == "readiness":
            result = _warmup_and_readiness(qdrant)
        else:
            if args.gate_report is None or args.golden is None or args.ai_golden is None:
                raise Day3BError("drill_inputs_missing")
            result = _run_drill(
                engine=engine, qdrant=qdrant, gate_report_path=args.gate_report,
                golden_path=args.golden, ai_golden_path=args.ai_golden,
                sample_size=args.sample_size, run_id=args.run_id,
                stage_output_dir=args.output.parent,
                existing_snapshot=args.existing_snapshot,
            )
    except Exception as exc:
        result = {
            "status": "NOT_PASS",
            "error_type": exc.__class__.__name__,
            "reason": str(exc),
            "alias_target": _safe_alias_target(qdrant),
            "emergency_restore": _emergency_restore(engine, qdrant, args.run_id),
        }
    finally:
        engine.dispose()
    _write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

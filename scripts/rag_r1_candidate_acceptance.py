from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.embedding_service import embed_batch_with_metadata
from backend.app.services.hybrid_retrieval_service import hybrid_retrieve
from backend.app.services.qdrant_security_contract import (
    qdrant_control_plane_issues,
    qdrant_security_status,
)
from backend.app.services.qdrant_vector_store import QdrantReadOnlyStore
from backend.app.services.rag_content_security import secure_candidates
from backend.app.services.rag_grounding_service import validate_candidate_citations
from backend.app.services.rag_qdrant_transport import sparse_query
from backend.app.services.rag_runtime_contract import RetrievalContext, runtime_contract_status
from backend.app.services.rerank_service import prewarm_reranker, rerank_candidates


RELEASE_ID = "RAG-R1"
COLLECTION = "rag_chunks_RAG-R1"
ALIAS = "rag_chunks_current"
TENANT_ID = "default"
EXPECTED_CHUNKS = 8339
READ_ONLY_REQUESTS = frozenset({
    ("GET", "/aliases"), ("GET", f"/collections/{quote(COLLECTION)}"),
    ("POST", f"/collections/{quote(COLLECTION)}/points/query"),
    ("POST", f"/collections/{quote(COLLECTION)}/points/scroll"),
})


class CandidateAcceptanceError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _stable_filter(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): ({str(op): "<time>" for op in item} if key == "range" and isinstance(item, Mapping) else _stable_filter(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_stable_filter(item) for item in value]
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateAcceptanceError(f"json_unavailable:{path.name}") from exc
    if not isinstance(value, dict):
        raise CandidateAcceptanceError(f"json_object_required:{path.name}")
    return value


def _read_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise CandidateAcceptanceError(f"env_unavailable:{path.name}")
    return {key: str(value or "") for key, value in dotenv_values(path).items()}


def _load_bm25(path: Path) -> dict[str, Any]:
    value = _read_json(path)
    base = dict(value)
    stored = str(base.pop("profile_sha256", ""))
    if (
        stored != hashlib.sha256(_canonical(base)).hexdigest()
        or value.get("chunk_count") != EXPECTED_CHUNKS
    ):
        raise CandidateAcceptanceError("bm25_profile_invalid")
    return value


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    rank = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return round(ordered[rank], 3)


def _distribution(values: Sequence[float]) -> dict[str, float]:
    normalized = [float(value) for value in values]
    if not normalized:
        return {key: 0.0 for key in ("p50_ms", "p90_ms", "p95_ms", "p99_ms", "max_ms")}
    return {
        "p50_ms": _percentile(normalized, 0.50),
        "p90_ms": _percentile(normalized, 0.90),
        "p95_ms": _percentile(normalized, 0.95),
        "p99_ms": _percentile(normalized, 0.99),
        "max_ms": round(max(normalized), 3),
    }


class CandidateQdrantReadOnlyTransport:
    """A deliberately non-public, exact-collection candidate evaluator transport."""

    def __init__(
        self,
        *,
        endpoint: str,
        ca_path: Path,
        read_only_key: str,
        bm25: Mapping[str, Any],
    ) -> None:
        if not endpoint.startswith("https://"):
            raise CandidateAcceptanceError("qdrant_https_endpoint_required")
        if not ca_path.is_file() or len(read_only_key) < 32:
            raise CandidateAcceptanceError("candidate_reader_profile_invalid")
        self.endpoint = endpoint.rstrip("/")
        self.context = ssl.create_default_context(cafile=str(ca_path))
        self._api_key = read_only_key
        self._bm25 = dict(bm25)
        self.request_count = 0
        self.write_count = 0
        self.methods_used: set[str] = set()
        self.paths_used: set[str] = set()
        self.filter_signatures: set[str] = set()
        self._metrics_lock = Lock()

    def _request(
        self,
        path: str,
        *,
        method: str,
        payload: Mapping[str, Any] | None = None,
        timeout: int = 30,
    ) -> Mapping[str, Any]:
        if (method, path) not in READ_ONLY_REQUESTS:
            with self._metrics_lock:
                self.write_count += int(method != "GET")
            raise CandidateAcceptanceError("candidate_read_path_rejected")
        data = _canonical(payload) if payload is not None else None
        headers = {"accept": "application/json", "api-key": self._api_key}
        if data is not None:
            headers["content-type"] = "application/json"
        request = Request(
            self.endpoint + path,
            data=data,
            headers=headers,
            method=method,
        )
        with self._metrics_lock:
            self.request_count += 1
            self.methods_used.add(method)
            self.paths_used.add(path)
        try:
            with urlopen(request, context=self.context, timeout=timeout) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise CandidateAcceptanceError(
                f"candidate_qdrant_http_{exc.code}"
            ) from exc
        except (OSError, UnicodeError) as exc:
            raise CandidateAcceptanceError("candidate_qdrant_read_unavailable") from exc
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise CandidateAcceptanceError("candidate_qdrant_response_invalid") from exc
        if not isinstance(parsed, Mapping):
            raise CandidateAcceptanceError("candidate_qdrant_response_invalid")
        return parsed

    def alias_target(self) -> str | None:
        body = self._request("/aliases", method="GET", timeout=10)
        aliases = body.get("result", {}).get("aliases")
        if not isinstance(aliases, list):
            raise CandidateAcceptanceError("candidate_alias_response_invalid")
        matches = [
            str(item.get("collection_name") or "")
            for item in aliases
            if isinstance(item, Mapping) and item.get("alias_name") == ALIAS
        ]
        if len(matches) > 1:
            raise CandidateAcceptanceError("candidate_alias_response_invalid")
        return matches[0] if matches else None

    def collection_state(self) -> dict[str, Any]:
        body = self._request(
            f"/collections/{quote(COLLECTION)}", method="GET", timeout=10
        )
        result = body.get("result")
        if not isinstance(result, Mapping):
            raise CandidateAcceptanceError("candidate_collection_state_invalid")
        stable = {
            "status": result.get("status"),
            "points_count": result.get("points_count"),
            "vectors_count": result.get("vectors_count"),
            "config": result.get("config"),
        }
        return {
            "points_count": int(result.get("points_count") or 0),
            "state_sha256": hashlib.sha256(_canonical(stable)).hexdigest(),
        }

    def query(
        self, *, collection: str, request: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if collection != COLLECTION:
            raise CandidateAcceptanceError("candidate_collection_rejected")
        with self._metrics_lock:
            self.filter_signatures.add(hashlib.sha256(_canonical(_stable_filter(request.get("filter")))).hexdigest())
        common = {
            "filter": request.get("filter"),
            "limit": max(1, min(int(request.get("limit") or 20), 100)),
            "with_payload": True,
            "with_vector": False,
        }
        mode = str(request.get("mode") or "")
        if mode == "dense":
            payload = {**common, "query": request.get("query"), "using": "dense"}
            body = self._request(
                f"/collections/{quote(COLLECTION)}/points/query",
                method="POST",
                payload=payload,
            )
        elif mode == "sparse":
            source = request.get("query")
            query_text = str(source.get("text") or "") if isinstance(source, Mapping) else ""
            vector = sparse_query(query_text, self._bm25)
            if not vector["indices"]:
                return {"points": []}
            body = self._request(
                f"/collections/{quote(COLLECTION)}/points/query",
                method="POST",
                payload={**common, "query": vector, "using": "bm25"},
            )
        elif mode == "structured":
            body = self._request(
                f"/collections/{quote(COLLECTION)}/points/scroll",
                method="POST",
                payload=common,
            )
        else:
            raise CandidateAcceptanceError("candidate_query_mode_invalid")
        points = body.get("result", {}).get("points")
        if not isinstance(points, list):
            raise CandidateAcceptanceError("candidate_qdrant_points_invalid")
        return {"points": points}


def _runtime_values(
    qdrant_env: Path, model_env: Path
) -> tuple[dict[str, str], dict[str, str]]:
    qdrant = _read_env(qdrant_env)
    model = _read_env(model_env)
    if issues := qdrant_control_plane_issues(qdrant):
        raise CandidateAcceptanceError(issues[0])
    read_key = qdrant.get("QDRANT_READ_ONLY_API_KEY", "")
    admin_key = qdrant.get("QDRANT_ADMIN_API_KEY", "")
    if not read_key or read_key == admin_key:
        raise CandidateAcceptanceError("candidate_reader_key_invalid")
    values = dict(model)
    values.update(
        {
            "RAG_QDRANT_API_KEY": read_key,
            "RAG_QDRANT_IMAGE_DIGEST": qdrant.get("QDRANT_IMAGE_DIGEST", ""),
        }
    )
    if "QDRANT_ADMIN_API_KEY" in values:
        raise CandidateAcceptanceError("candidate_admin_key_leak")
    status = runtime_contract_status(values)
    if status.issues:
        raise CandidateAcceptanceError("runtime_contract_unavailable:" + status.issues[0])
    security = qdrant_security_status(values)
    if security.issues or security.access_mode != "read_only":
        raise CandidateAcceptanceError("candidate_runtime_not_read_only")
    if (
        status.release.release_id != RELEASE_ID
        or status.release.collection != COLLECTION
        or status.release.alias != ALIAS
        or status.embedding.model != "BAAI/bge-large-zh-v1.5"
    ):
        raise CandidateAcceptanceError("candidate_runtime_identity_mismatch")
    return values, qdrant


def _load_gold(path: Path, corpus: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = _read_json(path)
    items = value.get("items")
    if (
        value.get("schema_version") != "rag-r1-retrieval-golden/v1"
        or value.get("release_id") != RELEASE_ID
        or value.get("collection") != COLLECTION
        or not isinstance(items, list)
        or len(items) != 50
    ):
        raise CandidateAcceptanceError("golden_set_contract_invalid")
    documents = {
        str(item["document_id"])
        for item in corpus["candidate_manifest"]["documents"]
    }
    chunks = {
        str(item["chunk_id"]): str(item["document_id"])
        for item in corpus["candidate_manifest"]["chunks"]
    }
    ids: set[str] = set()
    for item in items:
        item_id = str(item.get("id") or "")
        expected = [str(value) for value in item.get("expected_document_ids", [])]
        evidence = str(item.get("evidence_chunk_id") or "")
        if (
            not item_id
            or item_id in ids
            or not str(item.get("question") or "").strip()
            or not expected
            or any(document_id not in documents for document_id in expected)
            or evidence not in chunks
            or chunks[evidence] not in expected
            or not isinstance(item.get("critical"), bool)
        ):
            raise CandidateAcceptanceError(f"golden_item_invalid:{item_id or 'missing'}")
        ids.add(item_id)
    if sum(bool(item["critical"]) for item in items) < 10:
        raise CandidateAcceptanceError("critical_question_count_invalid")
    return [dict(item) for item in items]


def calculate_metrics(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(results)
    critical = [item for item in results if item.get("critical")]
    recall3 = sum(bool(item.get("hit_at_3")) for item in results)
    recall5 = sum(bool(item.get("hit_at_5")) for item in results)
    reciprocal = sum(float(item.get("reciprocal_rank") or 0.0) for item in results)
    citation = sum(bool(item.get("citation_integrity")) for item in results)
    critical_hits = sum(bool(item.get("hit_at_5")) for item in critical)
    latencies = [float(item.get("latency_ms") or 0.0) for item in results]
    hybrid_latencies = [float(item.get("hybrid_ms") or 0.0) for item in results]
    rerank_latencies = [float(item.get("rerank_ms") or 0.0) for item in results]
    stage_fields = {
        "auth_acl": "auth_acl_ms",
        "query_embedding": "query_embedding_ms",
        "sparse": "sparse_ms",
        "dense": "dense_ms",
        "qdrant": "qdrant_ms",
        "rrf": "rrf_ms",
        "duplicate_merge": "duplicate_merge_ms",
        "parent_expansion": "parent_expansion_ms",
        "content_security": "security_ms",
        "reranker": "rerank_ms",
        "citation_hash": "citation_ms",
        "postgres_metadata": "postgres_metadata_ms",
        "serialization": "serialization_ms",
        "cache": "cache_ms",
    }
    stage_latency_ms: dict[str, Any] = {}
    for stage, field in stage_fields.items():
        values = [
            float(item[field])
            for item in results
            if isinstance(item.get(field), (int, float))
            and not isinstance(item.get(field), bool)
        ]
        stage_latency_ms[stage] = {
            "sample_count": len(values),
            **(_distribution(values) if values else {"status": "not_measured"}),
        }
    denominator = max(1, total)
    critical_denominator = max(1, len(critical))
    return {
        "question_count": total,
        "critical_count": len(critical),
        "recall_at_3": round(recall3 / denominator, 4),
        "recall_at_5": round(recall5 / denominator, 4),
        "mrr": round(reciprocal / denominator, 4),
        "critical_recall_at_5": round(critical_hits / critical_denominator, 4),
        "citation_integrity": round(citation / denominator, 4),
        "latency_p50_ms": _percentile(latencies, 0.50),
        "latency_p90_ms": _percentile(latencies, 0.90),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "latency_p99_ms": _percentile(latencies, 0.99),
        "latency_max_ms": round(max(latencies), 3) if latencies else 0.0,
        "hybrid_p95_ms": _percentile(hybrid_latencies, 0.95),
        "rerank_p95_ms": _percentile(rerank_latencies, 0.95),
        "latency_distribution_ms": _distribution(latencies),
        "hybrid_distribution_ms": _distribution(hybrid_latencies),
        "reranker_distribution_ms": _distribution(rerank_latencies),
        "stage_latency_ms": stage_latency_ms,
    }


def _embedding_cache_key(
    questions: Sequence[Mapping[str, Any]], contract: Any
) -> str:
    value = {
        "questions": [
            {"id": item["id"], "question": item["question"]} for item in questions
        ],
        "provider": contract.embedding.provider,
        "model": contract.embedding.model,
        "version": contract.embedding.version,
        "dimension": contract.embedding.dimensions,
    }
    return hashlib.sha256(_canonical(value)).hexdigest()


def _embedding(
    question: Mapping[str, Any],
    contract: Any,
    cache_dir: Path | None,
) -> tuple[dict[str, Any], float, bool, float]:
    cache_key = _embedding_cache_key([question], contract)
    cache_path = cache_dir / f"{cache_key}.json" if cache_dir else None
    cache_started = time.perf_counter()
    if cache_path and cache_path.is_file():
        cached = _read_json(cache_path)
        value = cached.get("embedding")
        if (
            cached.get("schema_version") != "rag-r1-query-embedding/v2"
            or cached.get("cache_key") != cache_key
            or not isinstance(value, Mapping)
        ):
            raise CandidateAcceptanceError("query_embedding_cache_invalid")
        return dict(value), 0.0, True, round((time.perf_counter() - cache_started) * 1000.0, 3)
    cache_ms = round((time.perf_counter() - cache_started) * 1000.0, 3)
    started = time.perf_counter()
    values = embed_batch_with_metadata([str(question["question"])])
    if len(values) != 1:
        raise CandidateAcceptanceError("query_embedding_count_mismatch")
    embedding_ms = round((time.perf_counter() - started) * 1000.0, 3)
    if cache_path:
        cache_write_started = time.perf_counter()
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "schema_version": "rag-r1-query-embedding/v2",
                    "cache_key": cache_key,
                    "secret_values_emitted": False,
                    "embedding": values[0],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        cache_ms += round((time.perf_counter() - cache_write_started) * 1000.0, 3)
    return dict(values[0]), embedding_ms, False, round(cache_ms, 3)


def _gate(metrics: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    checks = {
        "question_count_50": metrics.get("question_count") == 50,
        "recall_at_3_gte_90pct": float(metrics.get("recall_at_3") or 0) >= 0.90,
        "recall_at_5_gte_98pct": float(metrics.get("recall_at_5") or 0) >= 0.98,
        "mrr_gte_85pct": float(metrics.get("mrr") or 0) >= 0.85,
        "critical_recall_100pct": metrics.get("critical_recall_at_5") == 1.0,
        "citation_integrity_100pct": metrics.get("citation_integrity") == 1.0,
        "latency_p95_lte_1500ms": float(metrics.get("latency_p95_ms") or 0) <= 1500.0,
        "read_only_key": runtime.get("access_mode") == "read_only",
        "read_paths_only": runtime.get("write_count") == 0
        and set(runtime.get("paths_used") or []).issubset(
            {path for _, path in READ_ONLY_REQUESTS}
        ),
        "acl_negative_denied": runtime.get("acl_negative_denied") is True,
        "candidate_alias_unchanged": runtime.get("alias_before")
        == runtime.get("alias_after")
        and runtime.get("alias_after") != COLLECTION,
        "candidate_collection_unchanged": runtime.get("collection_state_before")
        == runtime.get("collection_state_after")
        and int((runtime.get("collection_state_after") or {}).get("points_count") or 0)
        == EXPECTED_CHUNKS,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "passed": sum(bool(value) for value in checks.values()),
        "total": len(checks),
    }


def evaluate(
    *,
    qdrant_env: Path,
    model_env: Path,
    corpus_path: Path,
    questions_path: Path,
    embedding_cache: Path | None = None,
    run_state: str = "unspecified",
) -> dict[str, Any]:
    values, qdrant = _runtime_values(qdrant_env, model_env)
    corpus = _read_json(corpus_path)
    if (
        corpus.get("candidate_release_id") != RELEASE_ID
        or corpus.get("counts", {}).get("chunks") != EXPECTED_CHUNKS
        or len(corpus.get("candidate_manifest", {}).get("documents", [])) != 45
    ):
        raise CandidateAcceptanceError("candidate_corpus_identity_invalid")
    questions = _load_gold(questions_path, corpus)
    os.environ.update(values)
    contract = runtime_contract_status()
    contract.require_available()
    transport = CandidateQdrantReadOnlyTransport(
        endpoint=contract.qdrant.endpoint,
        ca_path=Path(values["RAG_QDRANT_TLS_CA_PATH"]),
        read_only_key=qdrant["QDRANT_READ_ONLY_API_KEY"],
        bm25=_load_bm25(corpus_path.parent / "bm25_profile.json"),
    )
    alias_before = transport.alias_target()
    collection_state_before = transport.collection_state()
    if alias_before == COLLECTION:
        raise CandidateAcceptanceError("candidate_already_published")
    acl_setup_started = time.perf_counter()
    context = RetrievalContext(
        tenant_id=TENANT_ID,
        user_id="rag-r1-acceptance",
        roles=("viewer",),
        acl_fingerprint=hashlib.sha256(b"rag-r1-acceptance").hexdigest(),
        release_id=RELEASE_ID,
    )
    store = QdrantReadOnlyStore(transport, contract.release, contract.embedding)
    acl_setup_ms = round((time.perf_counter() - acl_setup_started) * 1000.0, 3)
    prewarmed_reranker = None
    reranker_prewarm_ms = 0.0
    if run_state == "warm":
        prewarm_started = time.perf_counter()
        prewarmed_reranker = prewarm_reranker()
        reranker_prewarm_ms = round((time.perf_counter() - prewarm_started) * 1000.0, 3)

    results: list[dict[str, Any]] = []
    rerankers: set[str] = set()
    embedding_times: list[float] = []
    embedding_cache_times: list[float] = []
    embedding_cache_hits: list[bool] = []
    first_vector: list[float] = []
    for question_index, question in enumerate(questions, start=1):
        request_started = time.perf_counter()
        embedding, embedding_ms, cache_hit, embedding_cache_ms = _embedding(
            question, contract, embedding_cache
        )
        embedding_times.append(embedding_ms)
        embedding_cache_times.append(embedding_cache_ms)
        embedding_cache_hits.append(cache_hit)
        metadata = embedding.get("metadata") or {}
        vector = list(embedding.get("embedding") or [])
        if question_index == 1:
            first_vector = vector
        if (
            len(vector) != 1024
            or metadata.get("provider") != contract.embedding.provider
            or metadata.get("model") != contract.embedding.model
            or metadata.get("version") != contract.embedding.version
            or metadata.get("fallback")
        ):
            raise CandidateAcceptanceError(
                f"query_embedding_profile_mismatch:{question['id']}"
            )
        started = time.perf_counter()
        hybrid = hybrid_retrieve(
            store=store,
            context=context,
            query=str(question["question"]),
            dense_vector=vector,
            sparse_query={"text": str(question["question"])},
            structured_filter=None,
            requested_top_k=5,
        )
        hybrid_ms = round((time.perf_counter() - started) * 1000.0, 3)
        items: list[dict[str, Any]] = []
        reason = hybrid.reason
        reranker_name = ""
        citation_ok = False
        security_ms = 0.0
        rerank_ms = 0.0
        citation_ms = 0.0
        if hybrid.available:
            security_started = time.perf_counter()
            secured = secure_candidates(hybrid.items)
            security_ms = round((time.perf_counter() - security_started) * 1000.0, 3)
            reason = secured.reason
            if secured.available:
                prepared = [
                    {
                        **item,
                        "doc_id": item.get("document_id"),
                        "section_title": item.get("section_title") or "",
                    }
                    for item in secured.items
                ]
                rerank_started = time.perf_counter()
                reranked, reranker_name, rerank_error = rerank_candidates(
                    str(question["question"]), prepared
                )
                rerank_ms = round((time.perf_counter() - rerank_started) * 1000.0, 3)
                rerankers.add(reranker_name)
                if not rerank_error and reranker_name != "unavailable" and reranked:
                    for item in reranked:
                        item["final_score"] = float(item.get("final_score") or 0.0) * float(
                            item.get("security_score_multiplier") or 0.0
                        )
                    items = sorted(
                        reranked,
                        key=lambda item: float(item.get("final_score") or 0.0),
                        reverse=True,
                    )[:5]
                    citation_started = time.perf_counter()
                    citation_ok = validate_candidate_citations(items).available
                    citation_ms = round((time.perf_counter() - citation_started) * 1000.0, 3)
                    reason = "" if citation_ok else "citation_integrity_failed"
                else:
                    reason = "reranker_unavailable"
        retrieval_pipeline_ms = round((time.perf_counter() - started) * 1000.0, 3)
        expected = set(str(value) for value in question["expected_document_ids"])
        rankings = [str(item.get("document_id") or "") for item in items]
        rank = next(
            (index for index, document_id in enumerate(rankings, start=1) if document_id in expected),
            0,
        )
        hybrid_timings = dict(getattr(hybrid, "timings_ms", {}) or {})
        row = {
                "id": question["id"],
                "question": question["question"],
                "critical": question["critical"],
                "expected_document_ids": sorted(expected),
                "evidence_chunk_id": question["evidence_chunk_id"],
                "rank": rank or None,
                "hit_at_3": bool(rank and rank <= 3),
                "hit_at_5": bool(rank and rank <= 5),
                "reciprocal_rank": round(1.0 / rank, 4) if rank else 0.0,
                "citation_integrity": citation_ok,
                "latency_ms": 0.0,
                "retrieval_pipeline_ms": retrieval_pipeline_ms,
                "query_embedding_ms": embedding_ms,
                "cache_ms": embedding_cache_ms
                + float(hybrid_timings.get("cache_ms") or 0.0),
                "auth_acl_ms": round(
                    acl_setup_ms / len(questions)
                    + float(hybrid_timings.get("acl_ms") or 0.0),
                    3,
                ),
                "hybrid_ms": hybrid_ms,
                "dense_ms": hybrid_timings.get("dense_ms"),
                "sparse_ms": hybrid_timings.get("sparse_ms"),
                "qdrant_ms": hybrid_timings.get("qdrant_ms"),
                "rrf_ms": hybrid_timings.get("rrf_ms"),
                "duplicate_merge_ms": hybrid_timings.get("duplicate_merge_ms"),
                "parent_expansion_ms": hybrid_timings.get("parent_expansion_ms"),
                "postgres_metadata_ms": None,
                "security_ms": security_ms,
                "rerank_ms": rerank_ms,
                "citation_ms": citation_ms,
                "serialization_ms": 0.0,
                "reason": reason,
                "top_document_ids": rankings,
                "top_chunk_ids": [str(item.get("chunk_id") or "") for item in items],
                "candidate_counts": hybrid.candidate_counts,
                "reranker": reranker_name,
            }
        serialization_started = time.perf_counter()
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        serialization_ms = round(
            (time.perf_counter() - serialization_started) * 1000.0, 3
        )
        row["serialization_ms"] = serialization_ms
        row["latency_ms"] = round((time.perf_counter() - request_started) * 1000.0, 3)
        results.append(row)
        print(
            f"[{question_index:02d}/50] {question['id']} "
            f"rank={rank or '-'} citation={'ok' if citation_ok else 'fail'} "
            f"latency_ms={row['latency_ms']:.3f}",
            flush=True,
        )

    negative_context = RetrievalContext(
        tenant_id="rag-r1-denied-tenant", user_id="rag-r1-denied-user", roles=("viewer",),
        acl_fingerprint=hashlib.sha256(b"rag-r1-denied").hexdigest(), release_id=RELEASE_ID)
    acl_negative_started = time.perf_counter()
    negative = hybrid_retrieve(
        store=store, context=negative_context, query=str(questions[0]["question"]),
        dense_vector=first_vector, sparse_query={"text": str(questions[0]["question"])},
        structured_filter=None, requested_top_k=1,
    )
    acl_negative_ms = round((time.perf_counter() - acl_negative_started) * 1000.0, 3)
    acl_negative_denied = not negative.available and negative.reason == "no_evidence" and not negative.items
    alias_after = transport.alias_target()
    collection_state_after = transport.collection_state()
    metrics = calculate_metrics(results)
    runtime = {
        "release_id": RELEASE_ID,
        "collection": COLLECTION,
        "alias": ALIAS,
        "alias_before": alias_before,
        "alias_after": alias_after,
        "collection_state_before": collection_state_before,
        "collection_state_after": collection_state_after,
        "access_mode": contract.qdrant.access_mode,
        "tls_enabled": contract.qdrant.tls_enabled,
        "strict_mode": contract.qdrant.strict_mode,
        "admin_key_loaded_into_runtime": False,
        "secret_values_emitted": False,
        "request_count": transport.request_count,
        "write_count": transport.write_count,
        "methods_used": sorted(transport.methods_used),
        "paths_used": sorted(transport.paths_used),
        "acl_filter_signatures": sorted(transport.filter_signatures),
        "acl_policy_signature": hashlib.sha256(_canonical({
            "allowed_tenant": TENANT_ID, "denied_tenant": negative_context.tenant_id,
            "allowed_roles": list(context.roles), "allowed_fingerprint": context.acl_fingerprint, "denied_fingerprint": negative_context.acl_fingerprint, "release_id": RELEASE_ID,
        })).hexdigest(),
        "acl_negative_denied": acl_negative_denied,
        "acl_negative_check_ms": acl_negative_ms,
        "embedding_batch_ms": round(sum(embedding_times), 3),
        "embedding_average_ms": round(sum(embedding_times) / 50.0, 3),
        "embedding_cache_hit": bool(embedding_cache_hits) and all(embedding_cache_hits),
        "embedding_cache_total_ms": round(sum(embedding_cache_times), 3),
        "reranker_prewarm_ms": reranker_prewarm_ms,
        "prewarmed_reranker": getattr(prewarmed_reranker, "name", ""),
        "cold_start_total_ms": results[0]["latency_ms"] if run_state == "cold" else 0.0,
        "run_state": run_state,
        "latency_scope": "per_question_cache_embedding_retrieval_rerank_citation_serialization",
        "stage_coverage": {
            "auth": "not_in_prepublication_candidate_path",
            "acl": "retrieval_context_filter_and_payload_validation",
            "postgres_metadata": "not_in_prepublication_candidate_path",
            "query_embedding": "per_question_single_request",
            "serialization": "per_question_result_json",
        },
        "hardware": {
            "processor_count": os.cpu_count(),
            "device": values.get("RAG_RERANK_DEVICE", "cpu") or "cpu",
        },
        "embedding_profile": {
            "provider": contract.embedding.provider,
            "model": contract.embedding.model,
            "version": contract.embedding.version,
            "dimension": contract.embedding.dimensions,
            "batch_size": int(values.get("RAG_EMBEDDING_BATCH_SIZE") or 16),
        },
        "reranker_profile": {
            "provider": contract.reranker.provider,
            "model": contract.reranker.model,
            "version": contract.reranker.version,
            "batch_size": int(values.get("RAG_RERANK_BATCH_SIZE") or 8),
            "max_length": int(values.get("RAG_RERANK_MAX_LENGTH") or 512),
            "device": values.get("RAG_RERANK_DEVICE", "cpu") or "cpu",
        },
        "rerankers": sorted(rerankers),
    }
    return {
        "schema_version": "rag-r1-candidate-acceptance/v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "prepublication_candidate_read_only",
        "metrics": metrics,
        "runtime": runtime,
        "gate": _gate(metrics, runtime),
        "results": results,
    }


def _markdown(report: Mapping[str, Any]) -> str:
    metrics = report["metrics"]
    gate = report["gate"]
    failed = [name for name, value in gate["checks"].items() if not value]
    lines = [
        "# RAG-R1 候选版只读检索验收",
        "",
        f"- 结论：**{gate['status']}**",
        f"- 问题数：{metrics['question_count']}（关键 {metrics['critical_count']}）",
        f"- Recall@3：{metrics['recall_at_3']:.2%}",
        f"- Recall@5：{metrics['recall_at_5']:.2%}",
        f"- MRR：{metrics['mrr']:.2%}",
        f"- 关键问题 Recall@5：{metrics['critical_recall_at_5']:.2%}",
        f"- 引用完整性：{metrics['citation_integrity']:.2%}",
        f"- 检索 P50/P90/P95/P99/max：{metrics['latency_p50_ms']:.3f} / "
        f"{metrics['latency_p90_ms']:.3f} / {metrics['latency_p95_ms']:.3f} / "
        f"{metrics['latency_p99_ms']:.3f} / {metrics['latency_max_ms']:.3f} ms",
        "- 评测路径：候选物理集合 + TLS + 只读 Key；未切换别名。",
        "",
        "## 未通过项",
        "",
    ]
    lines.extend([f"- {item}" for item in failed] or ["- 无"])
    lines.extend(["", "## 逐题结果", "", "| ID | R@3 | R@5 | RR | 引用 | 延迟(ms) |", "|---|---:|---:|---:|---:|---:|"])
    for item in report["results"]:
        lines.append(
            f"| {item['id']} | {'是' if item['hit_at_3'] else '否'} | "
            f"{'是' if item['hit_at_5'] else '否'} | {item['reciprocal_rank']:.4f} | "
            f"{'是' if item['citation_integrity'] else '否'} | {item['latency_ms']:.3f} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate unpublished RAG-R1 candidate read-only")
    parser.add_argument("--qdrant-env", type=Path, required=True)
    parser.add_argument("--model-env", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--embedding-cache", type=Path)
    parser.add_argument(
        "--run-state", choices=("cold", "warm", "unspecified"), default="unspecified"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = evaluate(
            qdrant_env=args.qdrant_env.resolve(),
            model_env=args.model_env.resolve(),
            corpus_path=args.corpus.resolve(),
            questions_path=args.questions.resolve(),
            embedding_cache=args.embedding_cache.resolve() if args.embedding_cache else None,
            run_state=args.run_state,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        args.output.with_suffix(".md").write_text(_markdown(report), encoding="utf-8")
    except Exception as exc:
        print(f"RAG-R1 candidate acceptance FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"gate": report["gate"], "metrics": report["metrics"]}, ensure_ascii=False, indent=2))
    return 0 if report["gate"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

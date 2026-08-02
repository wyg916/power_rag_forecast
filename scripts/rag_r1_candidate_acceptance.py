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
from backend.app.services.rerank_service import rerank_candidates


RELEASE_ID = "RAG-R1"
COLLECTION = "rag_chunks_RAG-R1"
ALIAS = "rag_chunks_current"
TENANT_ID = "default"
EXPECTED_CHUNKS = 8339


class CandidateAcceptanceError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


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

    def _request(
        self,
        path: str,
        *,
        method: str,
        payload: Mapping[str, Any] | None = None,
        timeout: int = 30,
    ) -> Mapping[str, Any]:
        if method not in {"GET", "POST"}:
            raise CandidateAcceptanceError("candidate_write_method_rejected")
        if method == "POST" and not path.startswith(
            f"/collections/{quote(COLLECTION)}/points/"
        ):
            raise CandidateAcceptanceError("candidate_path_rejected")
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
        self.request_count += 1
        self.methods_used.add(method)
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

    def query(
        self, *, collection: str, request: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if collection != COLLECTION:
            raise CandidateAcceptanceError("candidate_collection_rejected")
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
        "latency_p95_ms": _percentile(latencies, 0.95),
        "hybrid_p95_ms": _percentile(hybrid_latencies, 0.95),
        "rerank_p95_ms": _percentile(rerank_latencies, 0.95),
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


def _embeddings(
    questions: Sequence[Mapping[str, Any]],
    contract: Any,
    cache_path: Path | None,
) -> tuple[list[dict[str, Any]], float, bool]:
    cache_key = _embedding_cache_key(questions, contract)
    if cache_path and cache_path.is_file():
        cached = _read_json(cache_path)
        values = cached.get("embeddings")
        if (
            cached.get("schema_version") != "rag-r1-query-embeddings/v1"
            or cached.get("cache_key") != cache_key
            or not isinstance(values, list)
            or len(values) != len(questions)
        ):
            raise CandidateAcceptanceError("query_embedding_cache_invalid")
        return [dict(item) for item in values], 0.0, True
    started = time.perf_counter()
    values = embed_batch_with_metadata(
        [str(item["question"]) for item in questions]
    )
    elapsed = round((time.perf_counter() - started) * 1000.0, 3)
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "schema_version": "rag-r1-query-embeddings/v1",
                    "cache_key": cache_key,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "secret_values_emitted": False,
                    "embeddings": values,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
    return values, elapsed, False


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
        "no_write_methods": runtime.get("write_count") == 0
        and set(runtime.get("methods_used") or []).issubset({"GET", "POST"}),
        "candidate_alias_unchanged": runtime.get("alias_before")
        == runtime.get("alias_after")
        and runtime.get("alias_after") != COLLECTION,
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
    if alias_before == COLLECTION:
        raise CandidateAcceptanceError("candidate_already_published")
    context = RetrievalContext(
        tenant_id=TENANT_ID,
        user_id="rag-r1-acceptance",
        roles=("viewer",),
        acl_fingerprint=hashlib.sha256(b"rag-r1-acceptance").hexdigest(),
        release_id=RELEASE_ID,
    )
    store = QdrantReadOnlyStore(transport, contract.release, contract.embedding)

    embeddings, embedding_ms, embedding_cache_hit = _embeddings(
        questions, contract, embedding_cache
    )
    if len(embeddings) != 50:
        raise CandidateAcceptanceError("query_embedding_count_mismatch")

    results: list[dict[str, Any]] = []
    rerankers: set[str] = set()
    for question_index, (question, embedding) in enumerate(
        zip(questions, embeddings), start=1
    ):
        metadata = embedding.get("metadata") or {}
        vector = list(embedding.get("embedding") or [])
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
        latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
        expected = set(str(value) for value in question["expected_document_ids"])
        rankings = [str(item.get("document_id") or "") for item in items]
        rank = next(
            (index for index, document_id in enumerate(rankings, start=1) if document_id in expected),
            0,
        )
        results.append(
            {
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
                "latency_ms": latency_ms,
                "hybrid_ms": hybrid_ms,
                "security_ms": security_ms,
                "rerank_ms": rerank_ms,
                "citation_ms": citation_ms,
                "reason": reason,
                "top_document_ids": rankings,
                "top_chunk_ids": [str(item.get("chunk_id") or "") for item in items],
                "candidate_counts": hybrid.candidate_counts,
                "reranker": reranker_name,
            }
        )
        print(
            f"[{question_index:02d}/50] {question['id']} "
            f"rank={rank or '-'} citation={'ok' if citation_ok else 'fail'} "
            f"latency_ms={latency_ms:.3f}",
            flush=True,
        )

    alias_after = transport.alias_target()
    metrics = calculate_metrics(results)
    runtime = {
        "release_id": RELEASE_ID,
        "collection": COLLECTION,
        "alias": ALIAS,
        "alias_before": alias_before,
        "alias_after": alias_after,
        "access_mode": contract.qdrant.access_mode,
        "tls_enabled": contract.qdrant.tls_enabled,
        "strict_mode": contract.qdrant.strict_mode,
        "admin_key_loaded_into_runtime": False,
        "secret_values_emitted": False,
        "request_count": transport.request_count,
        "write_count": transport.write_count,
        "methods_used": sorted(transport.methods_used),
        "embedding_batch_ms": embedding_ms,
        "embedding_average_ms": round(embedding_ms / 50.0, 3),
        "embedding_cache_hit": embedding_cache_hit,
        "rerankers": sorted(rerankers),
    }
    return {
        "schema_version": "rag-r1-candidate-acceptance/v1",
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
        f"- 检索 P95：{metrics['latency_p95_ms']:.3f} ms",
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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = evaluate(
            qdrant_env=args.qdrant_env.resolve(),
            model_env=args.model_env.resolve(),
            corpus_path=args.corpus.resolve(),
            questions_path=args.questions.resolve(),
            embedding_cache=args.embedding_cache.resolve() if args.embedding_cache else None,
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

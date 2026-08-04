from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Mapping, Sequence

from backend.app.services.qdrant_vector_store import QdrantReadOnlyStore
from backend.app.services.rag_runtime_contract import RetrievalContext


@dataclass(frozen=True)
class HybridResult:
    available: bool
    reason: str
    items: list[dict[str, Any]]
    top_k: int
    cache_key: str
    candidate_counts: dict[str, int]
    timings_ms: dict[str, float] = field(default_factory=dict)


def _timing_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000.0, 3)


def dynamic_k(query: str, requested: int = 5) -> int:
    value = str(query or "").lower()
    base = max(1, min(int(requested or 5), 20))
    broad = ("对比", "比较", "全部", "综合", "分别", "有哪些", "列表", "compare", "overview")
    focused = ("是什么", "什么是", "定义", "含义", "是否", "多少", "what is")
    if any(marker in value for marker in broad):
        return max(base, 8)
    if len(value) <= 40 and any(marker in value for marker in focused):
        return min(base, 3)
    return max(base, 5)


def release_aware_cache_key(
    *,
    context: RetrievalContext,
    store: QdrantReadOnlyStore,
    query: str,
    structured_filter: Mapping[str, Any],
    top_k: int,
) -> str:
    profile = store.embedding_profile
    value = {
        "tenant_id": context.tenant_id,
        "user_id": context.user_id,
        "roles": sorted(context.roles),
        "acl_fingerprint": context.acl_fingerprint,
        "release_id": store.release.release_id,
        "collection": store.release.collection,
        "embedding": {
            "provider": profile.provider,
            "model": profile.model,
            "version": profile.version,
            "dimension": profile.dimensions,
        },
        "query": str(query or "").strip(),
        "filter": structured_filter,
        "top_k": top_k,
    }
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "rag2:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _identity(item: Mapping[str, Any]) -> tuple[str, str, str] | None:
    value = (
        str(item.get("document_id") or ""),
        str(item.get("version_id") or ""),
        str(item.get("content_hash") or ""),
    )
    return value if all(value) else None


def rrf_fuse(
    candidate_sets: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    rank_constant: int = 60,
    limit: int | None = None,
    timings_ms: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    duplicate_started = perf_counter()
    grouped: dict[
        tuple[str, str, str], list[tuple[str, int, Mapping[str, Any]]]
    ] = {}
    for mode in sorted(candidate_sets):
        seen: set[tuple[str, str, str]] = set()
        for rank, source in enumerate(candidate_sets[mode], start=1):
            identity = _identity(source)
            if identity is None or identity in seen:
                continue
            seen.add(identity)
            grouped.setdefault(identity, []).append((mode, rank, source))
    if timings_ms is not None:
        timings_ms["duplicate_merge_ms"] = _timing_ms(duplicate_started)

    rrf_started = perf_counter()
    output: list[dict[str, Any]] = []
    for sources in grouped.values():
        first_mode, _, first_source = sources[0]
        current = {
            **dict(first_source),
            "rrf_score": 0.0,
            "retrieval_types": [first_mode],
        }
        for mode, rank, source in sources:
            current["rrf_score"] += 1.0 / (max(1, rank_constant) + rank)
            current["retrieval_types"] = sorted(
                {*current.get("retrieval_types", []), mode}
            )
            if float(source.get("score") or 0.0) > float(
                current.get("score") or 0.0
            ):
                for key, value in source.items():
                    if key not in {"rrf_score", "retrieval_types"}:
                        current[key] = value
        current["rrf_score"] = round(float(current["rrf_score"]), 9)
        current["final_score"] = current["rrf_score"]
        output.append(current)
    output.sort(
        key=lambda item: (
            -float(item.get("rrf_score") or 0.0),
            str(item.get("document_id") or ""),
            str(item.get("version_id") or ""),
            str(item.get("content_hash") or ""),
        )
    )
    if limit is not None:
        output = output[: max(0, int(limit))]
    if timings_ms is not None:
        timings_ms["rrf_ms"] = _timing_ms(rrf_started)

    parent_started = perf_counter()
    for item in output:
        parent = str(item.get("parent_content") or "").strip()
        child = str(item.get("content") or "").strip()
        item["context_content"] = f"{parent}\n\n{child}".strip() if parent else child
    if timings_ms is not None:
        timings_ms["parent_expansion_ms"] = _timing_ms(parent_started)
    return output


def hybrid_retrieve(
    *,
    store: QdrantReadOnlyStore,
    context: RetrievalContext,
    query: str,
    dense_vector: list[float] | None,
    sparse_query: Mapping[str, Any] | None,
    structured_filter: Mapping[str, Any] | None = None,
    requested_top_k: int = 5,
    candidate_limit: int | None = None,
) -> HybridResult:
    total_started = perf_counter()
    timings: dict[str, float] = {}
    filters = dict(structured_filter or {})
    top_k = dynamic_k(query, requested_top_k)
    rerank_limit = (
        top_k if candidate_limit is None else max(1, min(int(candidate_limit), 20))
    )
    search_limit = (
        max(20, min(top_k * 4, 100))
        if candidate_limit is None
        else max(8, min(rerank_limit * 4, 100))
    )
    cache_key_started = perf_counter()
    cache_key = release_aware_cache_key(
        context=context,
        store=store,
        query=query,
        structured_filter=filters,
        top_k=rerank_limit,
    )
    timings["cache_key_ms"] = _timing_ms(cache_key_started)
    timings["cache_ms"] = timings["cache_key_ms"]
    result = store.search(
        context=context,
        dense_vector=dense_vector,
        sparse_query=sparse_query,
        structured_filter=filters,
        limit=search_limit,
    )
    timings.update(result.timings_ms)
    counts = {key: len(value) for key, value in result.candidates.items()}
    counts["rerank_limit"] = rerank_limit
    counts["qdrant_per_mode_limit"] = search_limit
    if not result.available:
        timings["hybrid_total_ms"] = _timing_ms(total_started)
        return HybridResult(
            False,
            result.reason,
            [],
            top_k,
            cache_key,
            counts,
            timings,
        )
    items = rrf_fuse(
        result.candidates,
        limit=rerank_limit,
        timings_ms=timings,
    )
    counts["rerank_input"] = len(items)
    if not items:
        timings["hybrid_total_ms"] = _timing_ms(total_started)
        return HybridResult(
            False,
            "no_evidence",
            [],
            top_k,
            cache_key,
            counts,
            timings,
        )
    timings["hybrid_total_ms"] = _timing_ms(total_started)
    return HybridResult(True, "", items, top_k, cache_key, counts, timings)

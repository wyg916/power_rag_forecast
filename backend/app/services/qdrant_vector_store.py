from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from time import perf_counter
from typing import Any, Mapping, Protocol

from backend.app.services.rag_runtime_contract import (
    EmbeddingProfile,
    ReleaseIdentity,
    RetrievalContext,
)


class ReadOnlyQdrantTransport(Protocol):
    def query(self, *, collection: str, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class StoreResult:
    available: bool
    reason: str
    candidates: dict[str, list[dict[str, Any]]]
    request_count: int = 0
    timings_ms: dict[str, float] = field(default_factory=dict)


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return current if current.tzinfo else current.replace(tzinfo=timezone.utc)


def _timing_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000.0, 3)


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return _utc(parsed)
    except (TypeError, ValueError):
        return None


def _profile_issues(profile: EmbeddingProfile) -> tuple[str, ...]:
    issues: list[str] = []
    if profile.dimensions != 1024 or profile.expected_dimensions != 1024:
        issues.append("embedding_dimension_invalid")
    if not profile.version or profile.version != profile.expected_version:
        issues.append("embedding_version_mismatch")
    if profile.fallback_enabled:
        issues.append("embedding_fallback_forbidden")
    return tuple(issues)


class QdrantReadOnlyStore:
    _STRUCTURED_KEYS = {"domain", "source_types", "document_ids"}

    def __init__(
        self,
        transport: ReadOnlyQdrantTransport,
        release: ReleaseIdentity,
        embedding_profile: EmbeddingProfile,
    ) -> None:
        self._transport = transport
        self.release = release
        self.embedding_profile = embedding_profile

    def _issues(self, context: RetrievalContext) -> tuple[str, ...]:
        issues = [*context.issues(), *self.release.issues(), *_profile_issues(self.embedding_profile)]
        if context.release_id != self.release.release_id:
            issues.append("release_context_mismatch")
        return tuple(dict.fromkeys(issues))

    def _filter(
        self,
        context: RetrievalContext,
        now: datetime,
        structured: Mapping[str, Any],
    ) -> dict[str, Any]:
        must: list[dict[str, Any]] = [
            {"key": "tenant_id", "match": {"value": context.tenant_id}},
            {"key": "release_id", "match": {"value": self.release.release_id}},
            {"key": "status", "match": {"value": "published"}},
            {"key": "valid_from", "range": {"lte": now.isoformat()}},
            {"key": "embedding_provider", "match": {"value": self.embedding_profile.provider}},
            {"key": "embedding_model", "match": {"value": self.embedding_profile.model}},
            {"key": "embedding_version", "match": {"value": self.embedding_profile.version}},
            {"key": "embedding_dimension", "match": {"value": 1024}},
            {
                "min_should": {
                    "conditions": [
                        {"key": "acl_public", "match": {"value": True}},
                        {"key": "acl_user_ids", "match": {"value": context.user_id}},
                        {"key": "acl_roles", "match": {"any": list(context.roles)}},
                    ],
                    "min_count": 1,
                },
            },
            {
                "min_should": {
                    "conditions": [
                        {"key": "valid_to", "range": {"gt": now.isoformat()}},
                        {"is_empty": {"key": "valid_to"}},
                    ],
                    "min_count": 1,
                },
            },
        ]
        if structured.get("domain"):
            must.append({"key": "domain", "match": {"value": str(structured["domain"])}})
        for key, payload_key in (("source_types", "source_type"), ("document_ids", "document_id")):
            values = [str(item) for item in structured.get(key, []) if str(item)]
            if values:
                must.append({"key": payload_key, "match": {"any": values}})
        return {"must": must}

    def _payload_valid(
        self,
        payload: Mapping[str, Any],
        context: RetrievalContext,
        now: datetime,
    ) -> bool:
        valid_from = _parse_time(payload.get("valid_from"))
        valid_to_raw = payload.get("valid_to")
        valid_to = _parse_time(valid_to_raw)
        roles = {str(item) for item in payload.get("acl_roles", [])}
        users = {str(item) for item in payload.get("acl_user_ids", [])}
        acl_allowed = bool(payload.get("acl_public")) or context.user_id in users or bool(
            roles.intersection(context.roles)
        )
        return all(
            (
                payload.get("tenant_id") == context.tenant_id,
                payload.get("release_id") == self.release.release_id,
                payload.get("status") == "published",
                bool(str(payload.get("acl_fingerprint") or "").strip()),
                valid_from is not None and valid_from <= now,
                (not valid_to_raw) or (valid_to is not None and valid_to > now),
                acl_allowed,
                payload.get("embedding_provider") == self.embedding_profile.provider,
                payload.get("embedding_model") == self.embedding_profile.model,
                payload.get("embedding_version") == self.embedding_profile.version,
                payload.get("embedding_dimension") == 1024,
            )
        )

    def _candidates(
        self,
        mode: str,
        response: Mapping[str, Any],
        context: RetrievalContext,
        now: datetime,
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for point in response.get("points", []):
            payload = point.get("payload") if isinstance(point, Mapping) else None
            if not isinstance(payload, Mapping) or not self._payload_valid(payload, context, now):
                raise ValueError("payload_contract_violation")
            required = (
                "chunk_id",
                "document_id",
                "version_id",
                "content_hash",
                "content",
                "domain",
            )
            if any(not payload.get(key) for key in required):
                raise ValueError("candidate_identity_missing")
            output.append(
                {
                    **dict(payload),
                    "score": float(point.get("score") or 0.0),
                    "retrieval_type": mode,
                }
            )
        return output

    def search(
        self,
        *,
        context: RetrievalContext,
        dense_vector: list[float] | None,
        sparse_query: Mapping[str, Any] | None,
        structured_filter: Mapping[str, Any] | None,
        limit: int,
        now: datetime | None = None,
    ) -> StoreResult:
        total_started = perf_counter()
        timings: dict[str, float] = {}
        if issues := self._issues(context):
            timings["store_total_ms"] = _timing_ms(total_started)
            return StoreResult(False, issues[0], {}, 0, timings)
        structured = dict(structured_filter or {})
        if set(structured).difference(self._STRUCTURED_KEYS):
            timings["store_total_ms"] = _timing_ms(total_started)
            return StoreResult(False, "structured_filter_invalid", {}, 0, timings)
        current = _utc(now)
        requests: list[tuple[str, Any]] = []
        dense_started = perf_counter()
        if dense_vector is not None:
            if len(dense_vector) != 1024:
                timings["dense_prepare_ms"] = _timing_ms(dense_started)
                timings["store_total_ms"] = _timing_ms(total_started)
                return StoreResult(
                    False,
                    "query_embedding_dimension_mismatch",
                    {},
                    0,
                    timings,
                )
            try:
                normalized_dense = [float(value) for value in dense_vector]
            except (TypeError, ValueError):
                timings["dense_prepare_ms"] = _timing_ms(dense_started)
                timings["store_total_ms"] = _timing_ms(total_started)
                return StoreResult(False, "query_embedding_invalid", {}, 0, timings)
            if not all(isfinite(value) for value in normalized_dense) or not any(
                value != 0.0 for value in normalized_dense
            ):
                timings["dense_prepare_ms"] = _timing_ms(dense_started)
                timings["store_total_ms"] = _timing_ms(total_started)
                return StoreResult(False, "query_embedding_invalid", {}, 0, timings)
            requests.append(("dense", normalized_dense))
        timings["dense_prepare_ms"] = _timing_ms(dense_started)
        if sparse_query:
            requests.append(("sparse", dict(sparse_query)))
        if structured:
            requests.append(("structured", None))
        if not requests:
            timings["store_total_ms"] = _timing_ms(total_started)
            return StoreResult(False, "query_representation_missing", {}, 0, timings)

        filter_started = perf_counter()
        query_filter = self._filter(context, current, structured)
        timings["filter_ms"] = _timing_ms(filter_started)

        def execute(mode: str, query: Any) -> tuple[list[dict[str, Any]], float, float]:
            transport_started = perf_counter()
            response = self._transport.query(
                collection=self.release.collection,
                request={
                    "mode": mode,
                    "query": query,
                    "filter": query_filter,
                    "limit": max(1, min(int(limit), 200)),
                    "with_payload": True,
                    "with_vector": False,
                },
            )
            transport_ms = _timing_ms(transport_started)
            payload_started = perf_counter()
            values = self._candidates(mode, response, context, current)
            return values, transport_ms, _timing_ms(payload_started)

        completed: dict[str, tuple[list[dict[str, Any]], float, float]] = {}
        failures: dict[str, Exception] = {}
        qdrant_started = perf_counter()
        if len(requests) == 1:
            mode, query = requests[0]
            try:
                completed[mode] = execute(mode, query)
            except Exception as exc:
                failures[mode] = exc
        else:
            with ThreadPoolExecutor(
                max_workers=len(requests),
                thread_name_prefix="rag-qdrant-read",
            ) as executor:
                futures = {
                    executor.submit(execute, mode, query): mode
                    for mode, query in requests
                }
                for future in as_completed(futures):
                    mode = futures[future]
                    try:
                        completed[mode] = future.result()
                    except Exception as exc:
                        failures[mode] = exc
        timings["qdrant_wall_ms"] = _timing_ms(qdrant_started)
        timings["qdrant_ms"] = timings["qdrant_wall_ms"]

        if failures:
            first_error = next(
                failures[mode] for mode, _ in requests if mode in failures
            )
            reason = (
                str(first_error)
                if str(first_error)
                in {"payload_contract_violation", "candidate_identity_missing"}
                else "transport_unavailable"
            )
            timings["store_total_ms"] = _timing_ms(total_started)
            return StoreResult(False, reason, {}, len(requests), timings)

        candidates: dict[str, list[dict[str, Any]]] = {}
        payload_total = 0.0
        for mode, _ in requests:
            values, transport_ms, payload_ms = completed[mode]
            candidates[mode] = values
            timings[f"{mode}_ms"] = transport_ms
            timings[f"{mode}_payload_acl_ms"] = payload_ms
            payload_total += payload_ms
        timings["payload_acl_ms"] = round(payload_total, 3)
        timings["acl_ms"] = round(
            timings.get("filter_ms", 0.0) + timings["payload_acl_ms"],
            3,
        )
        available = bool(any(candidates.values()))
        timings["store_total_ms"] = _timing_ms(total_started)
        return StoreResult(
            available,
            "" if available else "no_evidence",
            candidates,
            len(requests),
            timings,
        )

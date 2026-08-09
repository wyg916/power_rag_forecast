from __future__ import annotations

import hashlib
import json
import ssl
import threading
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from dotenv import dotenv_values
from sqlalchemy import Engine, text

from backend.app.knowledge_enterprise_contracts import ReleaseCreateRequest
from backend.app.services.knowledge_enterprise_service import (
    EnterpriseKnowledgeConflict,
    EnterpriseKnowledgeUnavailable,
    EnterpriseRequestContext,
)
from backend.app.services.rag_release_service import (
    CURRENT_ALIAS,
    REQUIRED_RELEASE_GATES,
    AliasManifest,
    CollectionInspection,
    GateResult,
    ReleaseEmbeddingProfile,
    ReleaseFact,
    ReleaseOperation,
    ReleasePublisher,
    ReleaseRecord,
    ReleaseStatus,
)


_UNSET = object()
_ACTION_LOCK = threading.Lock()


def _qdrant_loopback_endpoint(port: str) -> str:
    return f"https://127.0.0.1:{port}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _gate_rows(report: Mapping[str, Any], release_id: str) -> tuple[GateResult, ...]:
    if report.get("release_id") != release_id:
        raise EnterpriseKnowledgeUnavailable("gate_report_release_mismatch")
    values = report.get("gates")
    if not isinstance(values, list):
        raise EnterpriseKnowledgeUnavailable("gate_report_invalid")
    rows: list[GateResult] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise EnterpriseKnowledgeUnavailable("gate_report_invalid")
        name = str(value.get("gate") or "")
        passed = value.get("passed")
        reason = str(value.get("reason") or value.get("reason_code") or "")
        if not name or not isinstance(passed, bool):
            raise EnterpriseKnowledgeUnavailable("gate_report_invalid")
        rows.append(GateResult(name, passed, reason))
    if len({row.gate for row in rows}) != len(rows):
        raise EnterpriseKnowledgeUnavailable("gate_report_duplicate")
    if {row.gate for row in rows} != REQUIRED_RELEASE_GATES:
        raise EnterpriseKnowledgeUnavailable("gate_report_incomplete")
    if any(not row.passed or row.reason for row in rows):
        raise EnterpriseKnowledgeUnavailable("gate_report_failed")
    return tuple(sorted(rows, key=lambda row: row.gate))


class QdrantReleaseAdmin:
    def __init__(self, env_file: Path):
        values = dotenv_values(env_file)
        root = Path(str(values.get("RAG_R1_QDRANT_ROOT") or "")).resolve()
        expected_root = Path("E:/智能运营分析项目_运行资产/rag-r1/qdrant").resolve()
        admin = str(values.get("QDRANT_ADMIN_API_KEY") or "")
        reader = str(values.get("QDRANT_READ_ONLY_API_KEY") or "")
        port = str(values.get("QDRANT_PORT") or "6333")
        if root != expected_root or not admin or admin == reader:
            raise EnterpriseKnowledgeUnavailable("qdrant_admin_profile_invalid")
        ca_path = root / "tls" / "ca-cert.pem"
        if not ca_path.is_file():
            raise EnterpriseKnowledgeUnavailable("qdrant_admin_ca_unavailable")
        # The compose profile is deliberately bound only to 127.0.0.1.  Using
        # localhost may resolve to ::1 first on Windows and turn a local
        # readiness read into a 45-second timeout even while Qdrant is healthy.
        self.endpoint = _qdrant_loopback_endpoint(port)
        self.api_key = admin
        self.context = ssl.create_default_context(cafile=str(ca_path))

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Mapping[str, Any] | None = None,
        timeout: float = 45,
    ) -> Mapping[str, Any]:
        request = Request(
            self.endpoint + path,
            data=_json(payload).encode("utf-8") if payload is not None else None,
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "api-key": self.api_key,
            },
            method=method,
        )
        try:
            with urlopen(request, context=self.context, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, HTTPError) as exc:
            raise EnterpriseKnowledgeUnavailable("qdrant_admin_unavailable") from exc
        if not isinstance(body, Mapping):
            raise EnterpriseKnowledgeUnavailable("qdrant_admin_response_invalid")
        return body

    def current_alias(self, alias: str) -> str | None:
        body = self._request("/aliases")
        values = body.get("result", {}).get("aliases", [])
        matches = [
            str(item.get("collection_name") or "")
            for item in values
            if isinstance(item, Mapping) and item.get("alias_name") == alias
        ]
        if len(matches) > 1:
            raise EnterpriseKnowledgeUnavailable("qdrant_alias_fact_invalid")
        return matches[0] if matches else None

    def _exact_count(self, collection: str, must: Sequence[Mapping[str, Any]]) -> int:
        body = self._request(
            f"/collections/{quote(collection)}/points/count",
            method="POST",
            payload={"filter": {"must": list(must)}, "exact": True},
        )
        return int(body.get("result", {}).get("count") or 0)

    def inspect_collection(self, collection: str) -> CollectionInspection:
        body = self._request(f"/collections/{quote(collection)}")
        result = body.get("result")
        if not isinstance(result, Mapping):
            raise EnterpriseKnowledgeUnavailable("qdrant_collection_fact_invalid")
        point_count = int(result.get("points_count") or 0)
        strict = bool((result.get("config", {}).get("strict_mode_config") or {}).get("enabled"))
        release_id = collection.removeprefix("rag_chunks_")
        profile = ReleaseEmbeddingProfile(
            "sentence_transformers",
            "BAAI/bge-large-zh-v1.5",
            self._single_payload_value(collection, "embedding_version"),
            1024,
            "bm25-zh-v1",
        )
        must = [
            {"key": "tenant_id", "match": {"value": "default"}},
            {"key": "release_id", "match": {"value": release_id}},
            {"key": "status", "match": {"value": "published"}},
            {"key": "embedding_provider", "match": {"value": profile.provider}},
            {"key": "embedding_model", "match": {"value": profile.model}},
            {"key": "embedding_version", "match": {"value": profile.version}},
            {"key": "embedding_dimension", "match": {"value": profile.dimension}},
            {"key": "sparse_profile", "match": {"value": profile.sparse_profile}},
        ]
        exact = self._exact_count(collection, must)
        profiles = (profile,) if point_count > 0 and exact == point_count else ()
        return CollectionInspection(
            collection=collection,
            point_count=point_count,
            strict_mode_enabled=strict,
            embedding_profile=profile,
            payload_embedding_profiles=profiles,
            payload_release_ids=frozenset({release_id}) if profiles else frozenset(),
            payload_tenant_ids=frozenset({"default"}) if profiles else frozenset(),
            payload_statuses=frozenset({"published"}) if profiles else frozenset(),
        )

    def _single_payload_value(self, collection: str, key: str) -> str:
        body = self._request(
            f"/collections/{quote(collection)}/facet",
            method="POST",
            payload={"key": key, "limit": 2, "exact": True},
        )
        hits = body.get("result", {}).get("hits", [])
        if not isinstance(hits, list) or len(hits) != 1:
            raise EnterpriseKnowledgeUnavailable("qdrant_payload_profile_invalid")
        return str(hits[0].get("value") or "")

    def snapshot_exists(self, collection: str, snapshot_id: str) -> bool:
        body = self._request(f"/collections/{quote(collection)}/snapshots")
        values = body.get("result") or []
        return any(isinstance(item, Mapping) and item.get("name") == snapshot_id for item in values)

    def snapshot_readable(self, collection: str, snapshot_id: str) -> bool:
        if not self.snapshot_exists(collection, snapshot_id):
            return False
        request = Request(
            self.endpoint
            + f"/collections/{quote(collection)}/snapshots/{quote(snapshot_id)}",
            headers={
                "accept": "application/octet-stream",
                "api-key": self.api_key,
                "range": "bytes=0-63",
            },
            method="GET",
        )
        try:
            with urlopen(request, context=self.context, timeout=120) as response:
                return response.status in {200, 206} and len(response.read(64)) > 0
        except (OSError, HTTPError):
            return False

    def create_snapshot(self, collection: str) -> str:
        before_body = self._request(f"/collections/{quote(collection)}/snapshots")
        before = {
            str(item.get("name") or "")
            for item in before_body.get("result") or []
            if isinstance(item, Mapping)
        }
        try:
            body = self._request(
                f"/collections/{quote(collection)}/snapshots?wait=true",
                method="POST",
                timeout=300,
            )
        except EnterpriseKnowledgeUnavailable:
            after_body = self._request(f"/collections/{quote(collection)}/snapshots")
            created = sorted(
                str(item.get("name") or "")
                for item in after_body.get("result") or []
                if isinstance(item, Mapping) and str(item.get("name") or "") not in before
            )
            if len(created) == 1 and self.snapshot_exists(collection, created[0]):
                return created[0]
            raise
        name = str((body.get("result") or {}).get("name") or "")
        if not name or not self.snapshot_exists(collection, name):
            raise EnterpriseKnowledgeUnavailable("qdrant_snapshot_create_failed")
        return name

    def switch_alias(
        self, alias: str, collection: str | None, *, expected_collection: str | None
    ) -> None:
        if self.current_alias(alias) != expected_collection:
            raise EnterpriseKnowledgeConflict("qdrant_alias_compare_and_swap_failed")
        actions: list[dict[str, Any]] = []
        if expected_collection is not None:
            actions.append({"delete_alias": {"alias_name": alias}})
        if collection is not None:
            actions.append(
                {"create_alias": {"collection_name": collection, "alias_name": alias}}
            )
        if actions:
            self._request("/collections/aliases", method="POST", payload={"actions": actions})
        if self.current_alias(alias) != collection:
            raise EnterpriseKnowledgeUnavailable("qdrant_alias_switch_unverified")

    def smoke(self, alias: str, release_id: str, collection: str) -> bool:
        return self.current_alias(alias) == collection and self._exact_count(
            alias,
            [
                {"key": "tenant_id", "match": {"value": "default"}},
                {"key": "release_id", "match": {"value": release_id}},
                {"key": "status", "match": {"value": "published"}},
            ],
        ) > 0


class PostgresReleaseStore:
    def __init__(self, engine: Engine, context: EnterpriseRequestContext):
        self.engine = engine
        self.context = context
        self._pending_current: object | str | None = _UNSET

    def _gate_pack(self, tenant_id: str, release_id: str) -> Mapping[str, Any]:
        with self.engine.connect() as connection:
            value = connection.execute(
                text(
                    """
                    SELECT details_json FROM kb_rag_audit_events
                    WHERE tenant_id=:tenant AND release_id=:release
                      AND event_type='release_gates_admitted' AND status='success'
                    ORDER BY created_at DESC LIMIT 1
                    """
                ),
                {"tenant": tenant_id, "release": release_id},
            ).scalar_one_or_none()
        return value if isinstance(value, Mapping) else {}

    def get_release(self, tenant_id: str, release_id: str) -> ReleaseRecord | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT tenant_id,release_id,status,collection_name,manifest_sha256,
                           embedding_provider,embedding_model,embedding_version,
                           embedding_dimension,sparse_profile,previous_release_id
                    FROM kb_releases WHERE tenant_id=:tenant AND release_id=:release
                    """
                ),
                {"tenant": tenant_id, "release": release_id},
            ).mappings().one_or_none()
        if row is None:
            return None
        try:
            status = ReleaseStatus(str(row["status"]))
        except ValueError as exc:
            raise EnterpriseKnowledgeUnavailable("release_status_invalid") from exc
        pack = self._gate_pack(tenant_id, release_id)
        gate_values = pack.get("gates") if isinstance(pack, Mapping) else []
        gates = tuple(
            GateResult(str(item["gate"]), bool(item["passed"]), str(item.get("reason") or ""))
            for item in gate_values or []
            if isinstance(item, Mapping)
        )
        return ReleaseRecord(
            tenant_id=str(row["tenant_id"]),
            release_id=str(row["release_id"]),
            status=status,
            collection=str(row["collection_name"]),
            alias=CURRENT_ALIAS,
            embedding_profile=ReleaseEmbeddingProfile(
                str(row["embedding_provider"]),
                str(row["embedding_model"]),
                str(row["embedding_version"]),
                int(row["embedding_dimension"]),
                str(row["sparse_profile"]),
            ),
            gates=gates,
            snapshot_id=str(pack.get("snapshot_id") or ""),
            previous_release_id=str(row["previous_release_id"] or ""),
            manifest_sha256=str(row["manifest_sha256"]),
        )

    def update_release(self, record: ReleaseRecord, *, expected_status: ReleaseStatus) -> None:
        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    UPDATE kb_releases SET status=:status, validated_at=CURRENT_TIMESTAMP,
                      updated_at=CURRENT_TIMESTAMP
                    WHERE tenant_id=:tenant AND release_id=:release AND status=:expected
                    """
                ),
                {
                    "status": record.status.value,
                    "tenant": record.tenant_id,
                    "release": record.release_id,
                    "expected": expected_status.value,
                },
            )
            if result.rowcount != 1:
                raise EnterpriseKnowledgeConflict("release_compare_and_swap_failed")

    def current_release_id(self, tenant_id: str) -> str | None:
        with self.engine.connect() as connection:
            return connection.execute(
                text("SELECT release_id FROM kb_releases WHERE tenant_id=:tenant AND is_current"),
                {"tenant": tenant_id},
            ).scalar_one_or_none()

    def set_current_release(
        self, tenant_id: str, release_id: str | None, *, expected_previous: str | None
    ) -> None:
        actual = (
            self._pending_current
            if self._pending_current is not _UNSET
            else self.current_release_id(tenant_id)
        )
        if actual != expected_previous:
            raise EnterpriseKnowledgeConflict("current_release_compare_and_swap_failed")
        self._pending_current = release_id

    def finalize_publish(
        self, published: ReleaseRecord, *, previous_release_id: str | None
    ) -> None:
        if self._pending_current != published.release_id:
            raise EnterpriseKnowledgeConflict("pending_current_fact_mismatch")
        with self.engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('rag-release-publish'))"))
            current = connection.execute(
                text("SELECT release_id FROM kb_releases WHERE tenant_id=:tenant AND is_current"),
                {"tenant": published.tenant_id},
            ).scalar_one_or_none()
            if current != previous_release_id:
                raise EnterpriseKnowledgeConflict("current_release_compare_and_swap_failed")
            if previous_release_id:
                result = connection.execute(
                    text(
                        """
                        UPDATE kb_releases SET status='superseded',is_current=false,
                          superseded_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                        WHERE tenant_id=:tenant AND release_id=:previous
                          AND status='published' AND is_current
                        """
                    ),
                    {"tenant": published.tenant_id, "previous": previous_release_id},
                )
                if result.rowcount != 1:
                    raise EnterpriseKnowledgeConflict("previous_release_compare_and_swap_failed")
            result = connection.execute(
                text(
                    """
                    UPDATE kb_releases SET status='published',is_current=true,
                      previous_release_id=:previous,published_at=CURRENT_TIMESTAMP,
                      rolled_back_at=NULL,updated_at=CURRENT_TIMESTAMP
                    WHERE tenant_id=:tenant AND release_id=:release AND status='validated'
                    """
                ),
                {
                    "tenant": published.tenant_id,
                    "release": published.release_id,
                    "previous": previous_release_id,
                },
            )
            if result.rowcount != 1:
                raise EnterpriseKnowledgeConflict("publish_finalize_compare_and_swap_failed")
        self._pending_current = _UNSET

    def finalize_rollback(
        self, rolled_back: ReleaseRecord, *, previous_release_id: str | None
    ) -> None:
        if self._pending_current != previous_release_id:
            raise EnterpriseKnowledgeConflict("pending_current_fact_mismatch")
        with self.engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('rag-release-publish'))"))
            result = connection.execute(
                text(
                    """
                    UPDATE kb_releases SET status='rolled_back',is_current=false,
                      rolled_back_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                    WHERE tenant_id=:tenant AND release_id=:release
                      AND status='published' AND is_current
                    """
                ),
                {"tenant": rolled_back.tenant_id, "release": rolled_back.release_id},
            )
            if result.rowcount != 1:
                raise EnterpriseKnowledgeConflict("rollback_finalize_compare_and_swap_failed")
            if previous_release_id:
                result = connection.execute(
                    text(
                        """
                        UPDATE kb_releases SET status='published',is_current=true,
                          published_at=CURRENT_TIMESTAMP,superseded_at=NULL,
                          updated_at=CURRENT_TIMESTAMP
                        WHERE tenant_id=:tenant AND release_id=:previous
                          AND status='superseded'
                        """
                    ),
                    {"tenant": rolled_back.tenant_id, "previous": previous_release_id},
                )
                if result.rowcount != 1:
                    raise EnterpriseKnowledgeConflict("rollback_previous_compare_and_swap_failed")
        self._pending_current = _UNSET

    def save_alias_manifest(self, manifest: AliasManifest) -> None:
        self._audit("alias_manifest_saved", manifest.release_id, "success", asdict(manifest))

    def append_fact(self, fact: ReleaseFact) -> None:
        self._audit(
            fact.event,
            fact.release_id,
            "failed" if fact.reason else "success",
            {"reason": fact.reason, **dict(fact.details or {})},
        )

    def _audit(
        self, event_type: str, release_id: str, status: str, details: Mapping[str, Any]
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO kb_rag_audit_events
                      (tenant_id,event_id,event_type,actor_id,resource_type,resource_id,
                       release_id,run_id,trace_id,status,details_json)
                    VALUES
                      (:tenant,:event,:type,:actor,'knowledge_release',:release,
                       :release,:run,:trace,:status,CAST(:details AS jsonb))
                    """
                ),
                {
                    "tenant": self.context.tenant_id,
                    "event": "evt_" + uuid.uuid4().hex,
                    "type": event_type,
                    "actor": self.context.actor_id,
                    "release": release_id,
                    "run": self.context.run_id,
                    "trace": self.context.trace_id,
                    "status": status,
                    "details": _json(details),
                },
            )

    def admit_gates(
        self,
        record: ReleaseRecord,
        gates: tuple[GateResult, ...],
        snapshot_id: str,
        report_sha256: str,
    ) -> None:
        existing = self._gate_pack(record.tenant_id, record.release_id)
        if existing:
            if (
                existing.get("gate_report_sha256") == report_sha256
                and existing.get("snapshot_id") == snapshot_id
            ):
                return
            raise EnterpriseKnowledgeConflict("release_gate_admission_conflict")
        self._audit(
            "release_gates_admitted",
            record.release_id,
            "success",
            {
                "gate_total": len(gates),
                "gate_passed": len(gates),
                "gates": [asdict(gate) for gate in gates],
                "snapshot_id": snapshot_id,
                "gate_report_sha256": report_sha256,
            },
        )


class NoopReleaseCache:
    def invalidate_release(self, tenant_id: str, release_id: str) -> None:
        return None


class RagReleaseWorkerRuntime:
    def __init__(self, engine: Engine, qdrant: QdrantReleaseAdmin):
        self.engine = engine
        self.qdrant = qdrant

    def _store(self, context: EnterpriseRequestContext) -> PostgresReleaseStore:
        if context.tenant_id != "default" or not all(
            (context.actor_id, context.run_id, context.trace_id)
        ):
            raise EnterpriseKnowledgeUnavailable("release_worker_context_invalid")
        return PostgresReleaseStore(self.engine, context)

    def admit(
        self,
        *,
        context: EnterpriseRequestContext,
        release_id: str,
        gate_report: Mapping[str, Any],
        gate_report_sha256: str,
        snapshot_id: str = "",
    ) -> dict[str, Any]:
        gates = _gate_rows(gate_report, release_id)
        canonical_hash = hashlib.sha256(_json(gate_report).encode("utf-8")).hexdigest()
        if canonical_hash != gate_report_sha256:
            raise EnterpriseKnowledgeUnavailable("gate_report_hash_mismatch")
        with _ACTION_LOCK:
            store = self._store(context)
            record = store.get_release(context.tenant_id, release_id)
            if record is None:
                raise EnterpriseKnowledgeUnavailable("release_not_found")
            if record.status not in {ReleaseStatus.CANDIDATE, ReleaseStatus.ROLLED_BACK}:
                raise EnterpriseKnowledgeConflict("release_gate_state_invalid")
            inspection = self.qdrant.inspect_collection(record.collection)
            if (
                inspection.point_count < 1
                or not inspection.strict_mode_enabled
                or inspection.embedding_profile != record.embedding_profile
                or inspection.payload_embedding_profiles != (record.embedding_profile,)
                or inspection.payload_release_ids != frozenset({record.release_id})
                or inspection.payload_tenant_ids != frozenset({record.tenant_id})
                or inspection.payload_statuses != frozenset({"published"})
            ):
                raise EnterpriseKnowledgeUnavailable("candidate_collection_admission_failed")
            existing = store._gate_pack(record.tenant_id, record.release_id)
            admitted_snapshot_id = str(existing.get("snapshot_id") or snapshot_id)
            if not admitted_snapshot_id:
                admitted_snapshot_id = self.qdrant.create_snapshot(record.collection)
            if not self.qdrant.snapshot_exists(record.collection, admitted_snapshot_id):
                raise EnterpriseKnowledgeUnavailable("snapshot_missing_after_create")
            if not self.qdrant.snapshot_readable(record.collection, admitted_snapshot_id):
                raise EnterpriseKnowledgeUnavailable("snapshot_unreadable_after_create")
            store.admit_gates(record, gates, admitted_snapshot_id, gate_report_sha256)
            return self.summary(store, release_id)

    def action(
        self,
        *,
        action: str,
        context: EnterpriseRequestContext,
        release_id: str,
        request_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        with _ACTION_LOCK:
            store = self._store(context)
            record = store.get_release(context.tenant_id, release_id)
            if record is None:
                raise EnterpriseKnowledgeUnavailable("release_not_found")
            if action == "create":
                request = ReleaseCreateRequest.model_validate(request_payload or {})
                if (
                    record.status is not ReleaseStatus.CANDIDATE
                    or record.manifest_sha256 != request.candidate_manifest_sha256
                    or record.embedding_profile.provider != request.embedding_profile.provider
                    or record.embedding_profile.model != request.embedding_profile.model
                    or record.embedding_profile.version != request.embedding_profile.version
                    or record.embedding_profile.dimension != request.embedding_profile.dimension
                    or record.embedding_profile.sparse_profile != request.embedding_profile.sparse_profile
                ):
                    raise EnterpriseKnowledgeConflict("release_create_fact_conflict")
                return self.summary(store, release_id)
            if action not in {"validate", "publish", "rollback"}:
                raise EnterpriseKnowledgeUnavailable("release_worker_action_invalid")
            publisher = ReleasePublisher(
                self.qdrant, store, NoopReleaseCache(), record.embedding_profile
            )
            operation: ReleaseOperation = getattr(publisher, action)(
                context.tenant_id, release_id
            )
            if not operation.succeeded:
                if operation.reason in {
                    "release_state_invalid", "release_validation_required",
                    "rollback_target_missing", "rollback_previous_invalid",
                }:
                    raise EnterpriseKnowledgeConflict(operation.reason)
                raise EnterpriseKnowledgeUnavailable(operation.reason or "release_action_failed")
            return self.summary(store, release_id)

    def summary(self, store: PostgresReleaseStore, release_id: str) -> dict[str, Any]:
        record = store.get_release("default", release_id)
        if record is None:
            raise EnterpriseKnowledgeUnavailable("release_not_found")
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT r.is_current,r.created_at,r.updated_at,r.validated_at,
                           r.published_at,r.rolled_back_at,
                           COUNT(*) FILTER (WHERE i.terminal_status='published') AS documents,
                           COALESCE(SUM(i.chunk_count),0) AS chunks,
                           COUNT(*) FILTER (WHERE i.terminal_status IN ('isolated','damaged')) AS isolated,
                           COUNT(*) FILTER (WHERE i.terminal_status='duplicate') AS duplicates
                    FROM kb_releases r LEFT JOIN kb_release_items i
                      ON i.tenant_id=r.tenant_id AND i.release_id=r.release_id
                    WHERE r.tenant_id='default' AND r.release_id=:release
                    GROUP BY r.tenant_id,r.release_id
                    """
                ),
                {"release": release_id},
            ).mappings().one()
        return {
            "release_id": release_id,
            "status": record.status.value,
            "is_current": bool(row["is_current"]),
            "documents": int(row["documents"] or 0),
            "chunks": int(row["chunks"] or 0),
            "isolated": int(row["isolated"] or 0),
            "duplicates": int(row["duplicates"] or 0),
            "gates": {
                "passed": sum(gate.passed for gate in record.gates),
                "total": len(record.gates),
            },
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
            "validated_at": row["validated_at"].isoformat() if row["validated_at"] else None,
            "published_at": row["published_at"].isoformat() if row["published_at"] else None,
            "rolled_back_at": row["rolled_back_at"].isoformat() if row["rolled_back_at"] else None,
        }

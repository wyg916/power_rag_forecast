from __future__ import annotations

import time
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, Sequence

from backend.app.services.rag_runtime_contract import ReleaseIdentity


CURRENT_ALIAS = "rag_chunks_current"
ROLLBACK_RTO_SECONDS = 300.0
REQUIRED_RELEASE_GATES = frozenset(
    {
        "ledger_terminal",
        "corpus_quality",
        "ocr_vlm_quality",
        "retrieval_quality",
        "ai_grounding",
        "security",
        "consistency",
        "reliability",
        "regression",
    }
)


class ReleaseStatus(str, Enum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True)
class ReleaseEmbeddingProfile:
    provider: str
    model: str
    version: str
    dimension: int
    sparse_profile: str

    def issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        if self.provider != "sentence_transformers":
            issues.append("embedding_provider_mismatch")
        if self.model not in {"bge-large-zh-v1.5", "BAAI/bge-large-zh-v1.5"}:
            issues.append("embedding_model_mismatch")
        if not self.version:
            issues.append("embedding_version_missing")
        if self.dimension != 1024:
            issues.append("embedding_dimension_mismatch")
        if not self.sparse_profile:
            issues.append("sparse_profile_missing")
        return tuple(issues)


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    reason: str = ""


@dataclass(frozen=True)
class ReleaseRecord:
    tenant_id: str
    release_id: str
    status: ReleaseStatus
    collection: str
    alias: str
    embedding_profile: ReleaseEmbeddingProfile
    gates: tuple[GateResult, ...]
    snapshot_id: str
    previous_release_id: str = ""


@dataclass(frozen=True)
class CollectionInspection:
    collection: str
    point_count: int
    embedding_profile: ReleaseEmbeddingProfile
    payload_embedding_profiles: tuple[ReleaseEmbeddingProfile, ...]
    payload_release_ids: frozenset[str]
    payload_tenant_ids: frozenset[str]
    payload_statuses: frozenset[str]


@dataclass(frozen=True)
class AliasManifest:
    tenant_id: str
    release_id: str
    alias: str
    before_collection: str | None
    after_collection: str
    previous_release_id: str | None
    snapshot_id: str
    snapshot_contains_alias: bool = False


@dataclass(frozen=True)
class ReleaseFact:
    tenant_id: str
    release_id: str
    event: str
    reason: str = ""
    details: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ReleaseOperation:
    succeeded: bool
    reason: str
    status: ReleaseStatus
    idempotent: bool
    elapsed_ms: int
    rto_met: bool
    consistency_restored: bool = True


class QdrantAdminControl(Protocol):
    def inspect_collection(self, collection: str) -> CollectionInspection: ...

    def snapshot_exists(self, collection: str, snapshot_id: str) -> bool: ...

    def current_alias(self, alias: str) -> str | None: ...

    def switch_alias(
        self,
        alias: str,
        collection: str | None,
        *,
        expected_collection: str | None,
    ) -> None: ...

    def smoke(self, alias: str, release_id: str, collection: str) -> bool: ...


class ReleaseFactStore(Protocol):
    def get_release(self, tenant_id: str, release_id: str) -> ReleaseRecord | None: ...

    def update_release(self, record: ReleaseRecord, *, expected_status: ReleaseStatus) -> None: ...

    def current_release_id(self, tenant_id: str) -> str | None: ...

    def set_current_release(
        self,
        tenant_id: str,
        release_id: str | None,
        *,
        expected_previous: str | None,
    ) -> None: ...

    def finalize_publish(
        self,
        published: ReleaseRecord,
        *,
        previous_release_id: str | None,
    ) -> None:
        """Atomically publish target and supersede previous, or change neither."""
        ...

    def finalize_rollback(
        self,
        rolled_back: ReleaseRecord,
        *,
        previous_release_id: str,
    ) -> None:
        """Atomically roll back target and republish previous, or change neither."""
        ...

    def save_alias_manifest(self, manifest: AliasManifest) -> None: ...

    def append_fact(self, fact: ReleaseFact) -> None: ...


class CacheInvalidator(Protocol):
    def invalidate_release(self, tenant_id: str, release_id: str) -> None: ...


class ReleasePublisher:
    def __init__(
        self,
        qdrant: QdrantAdminControl,
        store: ReleaseFactStore,
        cache: CacheInvalidator,
        expected_profile: ReleaseEmbeddingProfile,
        *,
        clock: Callable[[], float] = time.monotonic,
        required_gates: Sequence[str] = tuple(REQUIRED_RELEASE_GATES),
    ):
        self.qdrant = qdrant
        self.store = store
        self.cache = cache
        if issues := expected_profile.issues():
            raise ValueError("expected_embedding_profile_invalid:" + issues[0])
        self.expected_profile = expected_profile
        self.clock = clock
        self.required_gates = frozenset(required_gates)

    def _result(
        self,
        started: float,
        record: ReleaseRecord,
        succeeded: bool,
        reason: str = "",
        *,
        idempotent: bool = False,
        consistency_restored: bool = True,
    ) -> ReleaseOperation:
        elapsed_ms = max(0, int(round((self.clock() - started) * 1000)))
        return ReleaseOperation(
            succeeded,
            reason,
            record.status,
            idempotent,
            elapsed_ms,
            elapsed_ms <= int(ROLLBACK_RTO_SECONDS * 1000),
            consistency_restored,
        )

    def _fact(self, record: ReleaseRecord, event: str, reason: str = "", **details: Any) -> None:
        self.store.append_fact(
            ReleaseFact(record.tenant_id, record.release_id, event, reason, details or None)
        )

    def _preflight(self, record: ReleaseRecord) -> str:
        if record.tenant_id != "default":
            return "tenant_invalid"
        if identity_issues := ReleaseIdentity(
            record.release_id, record.collection, record.alias
        ).issues():
            return identity_issues[0]
        if record.embedding_profile != self.expected_profile:
            return "candidate_embedding_profile_mismatch"
        gates = {gate.gate: gate for gate in record.gates}
        if len(gates) != len(record.gates):
            return "release_gates_duplicate"
        if self.required_gates.difference(gates):
            return "release_gates_incomplete"
        if any(not gates[name].passed for name in self.required_gates):
            return "release_gate_failed"
        if not record.snapshot_id:
            return "snapshot_id_missing"
        try:
            inspection = self.qdrant.inspect_collection(record.collection)
            snapshot_exists = self.qdrant.snapshot_exists(record.collection, record.snapshot_id)
        except Exception:
            return "qdrant_preflight_unavailable"
        if inspection.collection != record.collection or inspection.point_count < 1:
            return "collection_identity_invalid"
        if inspection.embedding_profile != self.expected_profile:
            return "collection_embedding_profile_mismatch"
        if inspection.payload_embedding_profiles != (self.expected_profile,):
            return "payload_embedding_profile_mismatch"
        if inspection.payload_release_ids != frozenset({record.release_id}):
            return "payload_release_mismatch"
        if inspection.payload_tenant_ids != frozenset({record.tenant_id}):
            return "payload_tenant_mismatch"
        if inspection.payload_statuses != frozenset({"published"}):
            return "payload_status_mismatch"
        if not snapshot_exists:
            return "snapshot_missing"
        return ""

    def _load(self, tenant_id: str, release_id: str) -> ReleaseRecord:
        record = self.store.get_release(tenant_id, release_id)
        if record is None:
            raise LookupError("release_not_found")
        return record

    def _invalidate(self, record: ReleaseRecord, previous_release_id: str | None) -> None:
        self.cache.invalidate_release(record.tenant_id, record.release_id)
        if previous_release_id and previous_release_id != record.release_id:
            self.cache.invalidate_release(record.tenant_id, previous_release_id)

    def validate(self, tenant_id: str, release_id: str) -> ReleaseOperation:
        started = self.clock()
        record = self._load(tenant_id, release_id)
        if record.status is ReleaseStatus.VALIDATED:
            return self._result(started, record, True, idempotent=True)
        if record.status is not ReleaseStatus.CANDIDATE:
            return self._result(started, record, False, "release_state_invalid")
        if reason := self._preflight(record):
            self._fact(record, "validation_failed", reason)
            return self._result(started, record, False, reason)
        validated = replace(record, status=ReleaseStatus.VALIDATED)
        self.store.update_release(validated, expected_status=ReleaseStatus.CANDIDATE)
        self._fact(validated, "validated")
        return self._result(started, validated, True)

    def publish(self, tenant_id: str, release_id: str) -> ReleaseOperation:
        started = self.clock()
        record = self._load(tenant_id, release_id)
        if record.status is ReleaseStatus.PUBLISHED:
            consistent = (
                self.store.current_release_id(tenant_id) == release_id
                and self.qdrant.current_alias(record.alias) == record.collection
            )
            return self._result(
                started, record, consistent,
                "" if consistent else "published_state_inconsistent", idempotent=consistent,
                consistency_restored=consistent,
            )
        if record.status is not ReleaseStatus.VALIDATED:
            return self._result(started, record, False, "release_validation_required")
        if reason := self._preflight(record):
            self._fact(record, "publish_failed", reason)
            return self._result(started, record, False, reason)

        previous_release_id = self.store.current_release_id(tenant_id)
        before_collection = self.qdrant.current_alias(record.alias)
        expected_before = f"rag_chunks_{previous_release_id}" if previous_release_id else None
        if before_collection != expected_before:
            self._fact(record, "publish_failed", "current_alias_fact_mismatch")
            return self._result(started, record, False, "current_alias_fact_mismatch")
        previous: ReleaseRecord | None = None
        if previous_release_id:
            previous = self.store.get_release(tenant_id, previous_release_id)
            if (
                previous is None
                or previous.status is not ReleaseStatus.PUBLISHED
                or previous.collection != expected_before
            ):
                self._fact(record, "publish_failed", "previous_release_fact_invalid")
                return self._result(started, record, False, "previous_release_fact_invalid")
        manifest = AliasManifest(
            tenant_id, release_id, record.alias, before_collection, record.collection,
            previous_release_id, record.snapshot_id,
        )
        try:
            self.store.save_alias_manifest(manifest)
        except Exception:
            self._fact(record, "publish_failed", "alias_manifest_persist_failed")
            return self._result(started, record, False, "alias_manifest_persist_failed")
        try:
            self.qdrant.switch_alias(
                record.alias, record.collection, expected_collection=before_collection
            )
        except Exception:
            self._fact(record, "publish_failed", "alias_switch_failed")
            return self._result(started, record, False, "alias_switch_failed")
        try:
            self.store.set_current_release(
                tenant_id, release_id, expected_previous=previous_release_id
            )
        except Exception:
            restored = self._restore_alias(record, before_collection)
            self._invalidate(record, previous_release_id)
            reason = "postgres_current_failed" if restored else "postgres_failed_alias_rollback_failed"
            self._fact(record, "publish_failed", reason)
            return self._result(started, record, False, reason, consistency_restored=restored)

        smoke_ok = False
        try:
            smoke_ok = self.qdrant.smoke(record.alias, record.release_id, record.collection)
        except Exception:
            smoke_ok = False
        if not smoke_ok:
            restored = self._restore_publish(record, previous_release_id, before_collection)
            self._invalidate(record, previous_release_id)
            reason = "post_switch_smoke_failed" if restored else "smoke_atomic_rollback_failed"
            self._fact(record, "publish_failed", reason)
            return self._result(started, record, False, reason, consistency_restored=restored)

        published = replace(
            record, status=ReleaseStatus.PUBLISHED,
            previous_release_id=previous_release_id or "",
        )
        try:
            self.store.finalize_publish(
                published, previous_release_id=previous_release_id
            )
        except Exception:
            restored = self._restore_publish(record, previous_release_id, before_collection)
            self._invalidate(record, previous_release_id)
            reason = (
                "publish_finalize_failed"
                if restored
                else "publish_finalize_compensation_failed"
            )
            self._fact(record, "publish_failed", reason)
            return self._result(
                started, record, False, reason, consistency_restored=restored
            )
        self._invalidate(published, previous_release_id)
        self._fact(published, "published", alias_before=before_collection, alias_after=record.collection)
        return self._result(started, published, True)

    def _restore_alias(self, record: ReleaseRecord, before_collection: str | None) -> bool:
        try:
            self.qdrant.switch_alias(
                record.alias, before_collection, expected_collection=record.collection
            )
            return True
        except Exception:
            return False

    def _restore_publish(
        self,
        record: ReleaseRecord,
        previous_release_id: str | None,
        before_collection: str | None,
    ) -> bool:
        if not self._restore_alias(record, before_collection):
            return False
        try:
            self.store.set_current_release(
                record.tenant_id, previous_release_id, expected_previous=record.release_id
            )
            return True
        except Exception:
            try:
                self.qdrant.switch_alias(
                    record.alias, record.collection, expected_collection=before_collection
                )
            except Exception:
                pass
            return False

    def rollback(self, tenant_id: str, release_id: str) -> ReleaseOperation:
        started = self.clock()
        record = self._load(tenant_id, release_id)
        if record.status is ReleaseStatus.ROLLED_BACK:
            previous_collection = (
                f"rag_chunks_{record.previous_release_id}" if record.previous_release_id else None
            )
            consistent = (
                self.store.current_release_id(tenant_id) == record.previous_release_id
                and self.qdrant.current_alias(record.alias) == previous_collection
            )
            return self._result(
                started, record, consistent,
                "" if consistent else "rolled_back_state_inconsistent",
                idempotent=consistent, consistency_restored=consistent,
            )
        if record.status is not ReleaseStatus.PUBLISHED or not record.previous_release_id:
            return self._result(started, record, False, "rollback_target_missing")
        previous = self._load(tenant_id, record.previous_release_id)
        if previous.status is not ReleaseStatus.SUPERSEDED:
            return self._result(started, record, False, "rollback_previous_invalid")
        if (
            self.store.current_release_id(tenant_id) != record.release_id
            or self.qdrant.current_alias(record.alias) != record.collection
        ):
            return self._result(
                started, record, False, "published_state_inconsistent",
                consistency_restored=False,
            )
        try:
            self.qdrant.switch_alias(
                record.alias, previous.collection, expected_collection=record.collection
            )
        except Exception:
            self._fact(record, "rollback_failed", "rollback_alias_failed")
            return self._result(started, record, False, "rollback_alias_failed")
        try:
            self.store.set_current_release(
                tenant_id, previous.release_id, expected_previous=record.release_id
            )
        except Exception:
            restored = self._restore_alias(previous, record.collection)
            self._invalidate(record, previous.release_id)
            reason = "rollback_postgres_failed" if restored else "rollback_compensation_failed"
            self._fact(record, "rollback_failed", reason)
            return self._result(started, record, False, reason, consistency_restored=restored)
        smoke_ok = False
        try:
            smoke_ok = self.qdrant.smoke(record.alias, previous.release_id, previous.collection)
        except Exception:
            smoke_ok = False
        if not smoke_ok:
            restored = self._restore_rollback(record, previous)
            self._invalidate(record, previous.release_id)
            reason = "rollback_smoke_failed" if restored else "rollback_atomic_restore_failed"
            self._fact(record, "rollback_failed", reason)
            return self._result(started, record, False, reason, consistency_restored=restored)
        rolled_back = replace(record, status=ReleaseStatus.ROLLED_BACK)
        try:
            self.store.finalize_rollback(
                rolled_back, previous_release_id=previous.release_id
            )
        except Exception:
            restored = self._restore_rollback(record, previous)
            self._invalidate(record, previous.release_id)
            reason = (
                "rollback_finalize_failed"
                if restored
                else "rollback_finalize_compensation_failed"
            )
            self._fact(record, "rollback_failed", reason)
            return self._result(
                started, record, False, reason, consistency_restored=restored
            )
        self._invalidate(rolled_back, previous.release_id)
        self._fact(rolled_back, "rolled_back", alias_after=previous.collection)
        return self._result(started, rolled_back, True)

    def _restore_rollback(self, record: ReleaseRecord, previous: ReleaseRecord) -> bool:
        try:
            self.qdrant.switch_alias(
                record.alias, record.collection, expected_collection=previous.collection
            )
            self.store.set_current_release(
                record.tenant_id, record.release_id, expected_previous=previous.release_id
            )
            return True
        except Exception:
            return False

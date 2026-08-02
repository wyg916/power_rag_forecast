from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Callable, Protocol

from pydantic import ValidationError

from backend.app.knowledge_enterprise_contracts import (
    EmbeddingProfileContract,
    GateResultContract,
    ReleaseContract,
    ReleaseState,
)
from backend.app.services.knowledge_enterprise_service import (
    EnterpriseKnowledgeConflict,
    EnterpriseKnowledgeUnavailable,
    EnterpriseRequestContext,
)
from backend.app.services.rag_release_service import (
    CURRENT_ALIAS,
    REQUIRED_RELEASE_GATES,
    ReleaseFact,
    ReleaseOperation,
    ReleaseRecord,
    ReleaseStatus,
)
from backend.app.services.rag_runtime_contract import ReleaseIdentity, SHA256_PATTERN


_STATUS_MAP = {
    ReleaseStatus.CANDIDATE: ReleaseState.CANDIDATE,
    ReleaseStatus.VALIDATED: ReleaseState.VALIDATED,
    ReleaseStatus.PUBLISHED: ReleaseState.PUBLISHED,
    ReleaseStatus.SUPERSEDED: ReleaseState.SUPERSEDED,
    ReleaseStatus.ROLLED_BACK: ReleaseState.ROLLED_BACK,
}
_EXPECTED_STATUS = {
    "validate": ReleaseStatus.VALIDATED,
    "publish": ReleaseStatus.PUBLISHED,
    "rollback": ReleaseStatus.ROLLED_BACK,
}
_EXPECTED_EVENT = {
    "validate": "validated",
    "publish": "published",
    "rollback": "rolled_back",
}
_KNOWN_CONFLICTS = frozenset(
    {
        "release_state_invalid",
        "release_validation_required",
        "rollback_target_missing",
        "rollback_previous_invalid",
    }
)
_KNOWN_FAILURES = frozenset(
    {
        "tenant_invalid", "release_id_invalid", "release_collection_mismatch",
        "release_alias_invalid", "candidate_embedding_profile_mismatch",
        "release_manifest_invalid",
        "release_gates_duplicate", "release_gates_incomplete", "release_gate_failed",
        "snapshot_id_missing", "qdrant_preflight_unavailable", "collection_identity_invalid",
        "collection_strict_mode_required", "collection_embedding_profile_mismatch",
        "payload_embedding_profile_mismatch", "payload_release_mismatch",
        "payload_tenant_mismatch", "payload_status_mismatch", "snapshot_missing",
        "published_state_inconsistent", "rolled_back_state_inconsistent",
        "current_alias_fact_mismatch", "previous_release_fact_invalid",
        "alias_manifest_persist_failed", "alias_switch_failed", "postgres_current_failed",
        "postgres_failed_alias_rollback_failed", "post_switch_smoke_failed",
        "smoke_atomic_rollback_failed", "publish_finalize_failed",
        "publish_finalize_compensation_failed", "rollback_alias_failed",
        "rollback_postgres_failed", "rollback_compensation_failed", "rollback_smoke_failed",
        "rollback_atomic_restore_failed", "rollback_finalize_failed",
        "rollback_finalize_compensation_failed",
        "rollback_target_fact_invalid", "rollback_previous_fact_invalid",
    }
)


class ReleaseRuntimeService(Protocol):
    def validate(self, tenant_id: str, release_id: str) -> ReleaseOperation: ...

    def publish(self, tenant_id: str, release_id: str) -> ReleaseOperation: ...

    def rollback(self, tenant_id: str, release_id: str) -> ReleaseOperation: ...


class ReleaseAdapterFactStore(Protocol):
    def get_release(self, tenant_id: str, release_id: str) -> ReleaseRecord | None: ...

    def current_release_id(self, tenant_id: str) -> str | None: ...

    def append_fact(self, fact: ReleaseFact) -> None: ...

    def latest_fact(
        self, tenant_id: str, release_id: str, event: str
    ) -> ReleaseFact | None: ...


class ReleaseContractSource(Protocol):
    def get_release(
        self, *, tenant_id: str, release_id: str
    ) -> ReleaseContract | None: ...


class ReleaseFinalControlPlane(Protocol):
    def current_alias(self, alias: str) -> str | None: ...

    def smoke(self, alias: str, release_id: str, collection: str) -> bool: ...


class StrictReleasePublisherAdapter:
    """Maps verified RT4 release facts to the M5 ReleasePublisherPort contract."""

    def __init__(
        self,
        service: ReleaseRuntimeService,
        facts: ReleaseAdapterFactStore,
        contracts: ReleaseContractSource,
        control_plane: ReleaseFinalControlPlane,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.service = service
        self.facts = facts
        self.contracts = contracts
        self.control_plane = control_plane
        self.clock = clock

    def validate(
        self, *, context: EnterpriseRequestContext, release_id: str
    ) -> ReleaseContract:
        return self._act("validate", context, release_id)

    def publish(
        self, *, context: EnterpriseRequestContext, release_id: str
    ) -> ReleaseContract:
        return self._act("publish", context, release_id)

    def rollback(
        self, *, context: EnterpriseRequestContext, release_id: str
    ) -> ReleaseContract:
        return self._act("rollback", context, release_id)

    @staticmethod
    def _check_context(context: EnterpriseRequestContext, release_id: str) -> None:
        if (
            context.tenant_id != "default"
            or not context.actor_id
            or not context.run_id
            or not context.trace_id
            or not release_id
            or ReleaseIdentity(
                release_id, f"rag_chunks_{release_id}", CURRENT_ALIAS
            ).issues()
        ):
            raise EnterpriseKnowledgeUnavailable("release_adapter_context_invalid")

    def _seed(self, context: EnterpriseRequestContext, release_id: str) -> ReleaseContract:
        try:
            value = self.contracts.get_release(
                tenant_id=context.tenant_id, release_id=release_id
            )
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("release_contract_fact_unavailable") from exc
        if value is None:
            raise EnterpriseKnowledgeUnavailable("release_contract_fact_missing")
        try:
            seed = ReleaseContract.model_validate(value)
        except ValidationError as exc:
            raise EnterpriseKnowledgeUnavailable("release_contract_fact_invalid") from exc
        if seed.tenant_id != context.tenant_id or seed.release_id != release_id:
            raise EnterpriseKnowledgeUnavailable("release_contract_fact_identity_mismatch")
        return seed

    def _operation(
        self, action: str, context: EnterpriseRequestContext, release_id: str
    ) -> ReleaseOperation:
        try:
            value = getattr(self.service, action)(context.tenant_id, release_id)
        except EnterpriseKnowledgeConflict:
            raise
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable(f"release_{action}_unavailable") from exc
        if (
            not isinstance(value, ReleaseOperation)
            or not isinstance(value.succeeded, bool)
            or not isinstance(value.idempotent, bool)
            or not isinstance(value.rto_met, bool)
            or not isinstance(value.consistency_restored, bool)
            or not isinstance(value.status, ReleaseStatus)
            or not isinstance(value.reason, str)
            or not isinstance(value.elapsed_ms, int)
            or value.elapsed_ms < 0
        ):
            raise EnterpriseKnowledgeUnavailable("release_operation_contract_invalid")
        if not value.succeeded:
            if value.reason in _KNOWN_CONFLICTS:
                raise EnterpriseKnowledgeConflict(value.reason)
            reason = value.reason if value.reason in _KNOWN_FAILURES else "unknown"
            raise EnterpriseKnowledgeUnavailable(
                f"release_{action}_failed:{reason}"
            )
        if value.reason or value.status is not _EXPECTED_STATUS[action]:
            raise EnterpriseKnowledgeUnavailable("release_operation_state_mismatch")
        if not value.consistency_restored:
            raise EnterpriseKnowledgeUnavailable("release_operation_consistency_unrestored")
        if not value.rto_met:
            raise EnterpriseKnowledgeUnavailable(f"release_{action}_rto_failed")
        return value

    def _record(
        self,
        context: EnterpriseRequestContext,
        release_id: str,
        expected_profile: EmbeddingProfileContract,
    ) -> ReleaseRecord:
        try:
            record = self.facts.get_release(context.tenant_id, release_id)
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("release_record_unavailable") from exc
        if not isinstance(record, ReleaseRecord):
            raise EnterpriseKnowledgeUnavailable("release_record_missing_or_invalid")
        if record.tenant_id != context.tenant_id or record.release_id != release_id:
            raise EnterpriseKnowledgeUnavailable("release_record_identity_mismatch")
        gates = tuple(record.gates)
        profile = record.embedding_profile
        if (
            ReleaseIdentity(record.release_id, record.collection, record.alias).issues()
            or not SHA256_PATTERN.fullmatch(record.manifest_sha256)
            or profile.issues()
            or (
                profile.provider,
                profile.model,
                profile.version,
                profile.dimension,
                profile.sparse_profile,
            )
            != (
                expected_profile.provider,
                expected_profile.model,
                expected_profile.version,
                expected_profile.dimension,
                expected_profile.sparse_profile,
            )
            or not record.snapshot_id
            or len({gate.gate for gate in gates}) != len(gates)
            or {gate.gate for gate in gates} != REQUIRED_RELEASE_GATES
            or any(gate.passed is not True or gate.reason for gate in gates)
        ):
            raise EnterpriseKnowledgeUnavailable("release_record_basic_gate_failed")
        return record

    def _operation_fact(
        self,
        action: str,
        context: EnterpriseRequestContext,
        release_id: str,
        expected_collection: str | None,
    ) -> ReleaseFact:
        try:
            fact = self.facts.latest_fact(
                context.tenant_id, release_id, _EXPECTED_EVENT[action]
            )
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("release_final_fact_unavailable") from exc
        if not isinstance(fact, ReleaseFact):
            raise EnterpriseKnowledgeUnavailable("release_final_fact_missing_or_invalid")
        if (
            fact.tenant_id != context.tenant_id
            or fact.release_id != release_id
            or fact.event != _EXPECTED_EVENT[action]
            or fact.reason
        ):
            raise EnterpriseKnowledgeUnavailable("release_final_fact_mismatch")
        if fact.details is not None and not isinstance(fact.details, Mapping):
            raise EnterpriseKnowledgeUnavailable("release_final_fact_mismatch")
        try:
            alias_after = (fact.details or {}).get("alias_after")
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("release_final_fact_mismatch") from exc
        if (action == "validate" and alias_after not in {None, ""}) or (
            action != "validate" and alias_after != expected_collection
        ):
            raise EnterpriseKnowledgeUnavailable("release_final_fact_alias_mismatch")
        return fact

    def _current_and_alias(
        self,
        action: str,
        context: EnterpriseRequestContext,
        record: ReleaseRecord,
        expected_profile: EmbeddingProfileContract,
    ) -> str | None:
        try:
            current_id = self.facts.current_release_id(context.tenant_id)
            alias_collection = self.control_plane.current_alias(CURRENT_ALIAS)
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("release_final_state_unavailable") from exc
        if action == "publish":
            expected_id, expected_collection = record.release_id, record.collection
        elif action == "rollback":
            if record.previous_release_id:
                previous = self._record(
                    context, record.previous_release_id, expected_profile
                )
                if previous.status is not ReleaseStatus.PUBLISHED:
                    raise EnterpriseKnowledgeUnavailable("rollback_previous_fact_invalid")
                expected_id, expected_collection = previous.release_id, previous.collection
            else:
                expected_id, expected_collection = None, None
        else:
            if current_id == record.release_id:
                raise EnterpriseKnowledgeUnavailable("validated_release_is_current")
            if current_id:
                current = self._record(context, current_id, expected_profile)
                if current.status is not ReleaseStatus.PUBLISHED:
                    raise EnterpriseKnowledgeUnavailable("current_release_fact_invalid")
                expected_collection = current.collection
            else:
                expected_collection = None
            expected_id = current_id
        if current_id != expected_id or alias_collection != expected_collection:
            raise EnterpriseKnowledgeUnavailable("release_current_alias_fact_mismatch")
        if action == "publish" or (action == "rollback" and expected_collection):
            try:
                smoke_ok = self.control_plane.smoke(
                    CURRENT_ALIAS, expected_id, expected_collection
                )
            except Exception as exc:
                raise EnterpriseKnowledgeUnavailable("release_final_smoke_unavailable") from exc
            if smoke_ok is not True:
                raise EnterpriseKnowledgeUnavailable("release_final_smoke_failed")
        return expected_collection

    def _contract(
        self,
        action: str,
        context: EnterpriseRequestContext,
        seed: ReleaseContract,
        record: ReleaseRecord,
    ) -> ReleaseContract:
        if record.status is not _EXPECTED_STATUS[action]:
            raise EnterpriseKnowledgeUnavailable("release_record_state_mismatch")
        if (
            record.alias != CURRENT_ALIAS
            or record.collection != f"rag_chunks_{record.release_id}"
            or record.embedding_profile.issues()
            or not SHA256_PATTERN.fullmatch(record.manifest_sha256)
            or seed.manifest_sha256 != record.manifest_sha256
        ):
            raise EnterpriseKnowledgeUnavailable("release_record_contract_mismatch")
        gates = tuple(record.gates)
        names = {gate.gate for gate in gates}
        if (
            len(names) != len(gates)
            or names != REQUIRED_RELEASE_GATES
            or any(gate.passed is not True or gate.reason for gate in gates)
        ):
            raise EnterpriseKnowledgeUnavailable("release_gate_fact_mismatch")
        try:
            profile = EmbeddingProfileContract(
                provider=record.embedding_profile.provider,
                model=record.embedding_profile.model,
                version=record.embedding_profile.version,
                dimension=record.embedding_profile.dimension,
                sparse_profile=record.embedding_profile.sparse_profile,
            )
            if (
                seed.collection != record.collection
                or seed.alias != record.alias
                or seed.embedding_profile != profile
            ):
                raise ValueError("seed_record_mismatch")
            updated_at = self.clock()
            if updated_at.tzinfo is None:
                raise ValueError("timezone_required")
            return ReleaseContract(
                release_id=record.release_id,
                tenant_id=record.tenant_id,
                status=_STATUS_MAP[record.status],
                collection=record.collection,
                alias=record.alias,
                manifest_sha256=seed.manifest_sha256,
                embedding_profile=profile,
                gates=[
                    GateResultContract(
                        gate=gate.gate,
                        passed=gate.passed,
                        reason_code=gate.reason,
                    )
                    for gate in gates
                ],
                run_id=context.run_id,
                trace_id=context.trace_id,
                created_at=seed.created_at,
                updated_at=updated_at,
            )
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("release_contract_conversion_failed") from exc

    def _persist_trace(
        self,
        action: str,
        context: EnterpriseRequestContext,
        operation: ReleaseOperation,
        contract: ReleaseContract,
    ) -> None:
        event = f"enterprise_{action}_completed"
        details = {
            "action": action,
            "status": contract.status.value,
            "run_id": context.run_id,
            "trace_id": context.trace_id,
            "manifest_sha256": contract.manifest_sha256,
            "idempotent": operation.idempotent,
        }
        fact = ReleaseFact(
            context.tenant_id, contract.release_id, event, details=details
        )
        try:
            self.facts.append_fact(fact)
            persisted = self.facts.latest_fact(
                context.tenant_id, contract.release_id, event
            )
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("release_trace_fact_unavailable") from exc
        if not isinstance(persisted, ReleaseFact) or (
            persisted.details is not None and not isinstance(persisted.details, Mapping)
        ):
            raise EnterpriseKnowledgeUnavailable("release_trace_fact_mismatch")
        if (
            persisted.tenant_id != context.tenant_id
            or persisted.release_id != contract.release_id
            or persisted.event != event
            or persisted.reason
            or persisted.details != details
        ):
            raise EnterpriseKnowledgeUnavailable("release_trace_fact_mismatch")

    def _act(
        self, action: str, context: EnterpriseRequestContext, release_id: str
    ) -> ReleaseContract:
        try:
            self._check_context(context, release_id)
            seed = self._seed(context, release_id)
            operation = self._operation(action, context, release_id)
            record = self._record(context, release_id, seed.embedding_profile)
            if operation.status is not record.status:
                raise EnterpriseKnowledgeUnavailable("release_operation_record_mismatch")
            expected_collection = self._current_and_alias(
                action, context, record, seed.embedding_profile
            )
            self._operation_fact(action, context, release_id, expected_collection)
            contract = self._contract(action, context, seed, record)
            self._persist_trace(action, context, operation, contract)
            return contract
        except (EnterpriseKnowledgeUnavailable, EnterpriseKnowledgeConflict):
            raise
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("release_adapter_unavailable") from exc

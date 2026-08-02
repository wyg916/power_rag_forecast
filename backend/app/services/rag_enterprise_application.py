from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol, Sequence

from pydantic import ValidationError

from backend.app.knowledge_enterprise_contracts import (
    IngestionContract,
    IngestionCreateRequest,
    IngestionState,
    ReleaseContract,
    ReleaseCreateRequest,
    ReleaseState,
)
from backend.app.services.knowledge_enterprise_service import (
    EnterpriseKnowledgeConflict,
    EnterpriseKnowledgeUnavailable,
    EnterpriseRequestContext,
)


@dataclass(frozen=True)
class StoredContent:
    tenant_id: str
    content_id: str
    content_sha256: str
    size_bytes: int


@dataclass(frozen=True)
class IngestionIdempotencyFact:
    idempotency_key: str
    content_sha256: str
    contract: IngestionContract


@dataclass(frozen=True)
class ReleaseIdempotencyFact:
    idempotency_key: str
    request_sha256: str
    contract: ReleaseContract


class ImmutableContentStore(Protocol):
    def put_immutable(
        self, *, tenant_id: str, content_sha256: str, content: bytes
    ) -> StoredContent: ...


class IngestionFactStore(Protocol):
    def find_idempotency(
        self, *, tenant_id: str, idempotency_key: str
    ) -> IngestionIdempotencyFact | None: ...

    def create_draft_atomic(
        self,
        *,
        context: EnterpriseRequestContext,
        request: IngestionCreateRequest,
        stored_content: StoredContent,
        now: datetime,
    ) -> IngestionIdempotencyFact: ...

    def get_ingestion(
        self, *, tenant_id: str, ingestion_id: str
    ) -> IngestionContract | None: ...


class ApplicationReleaseFactStore(Protocol):
    def find_idempotency(
        self, *, tenant_id: str, idempotency_key: str
    ) -> ReleaseIdempotencyFact | None: ...

    def create_candidate_atomic(
        self,
        *,
        context: EnterpriseRequestContext,
        request: ReleaseCreateRequest,
        request_sha256: str,
        now: datetime,
    ) -> ReleaseIdempotencyFact: ...

    def get_release(
        self, *, tenant_id: str, release_id: str
    ) -> ReleaseContract | None: ...

    def list_releases(self, *, tenant_id: str) -> Sequence[ReleaseContract]: ...


class ReleasePublisherPort(Protocol):
    def validate(
        self, *, context: EnterpriseRequestContext, release_id: str
    ) -> object: ...

    def publish(
        self, *, context: EnterpriseRequestContext, release_id: str
    ) -> object: ...

    def rollback(
        self, *, context: EnterpriseRequestContext, release_id: str
    ) -> object: ...


def _request_sha256(request: ReleaseCreateRequest) -> str:
    payload = request.model_dump(mode="json", exclude={"idempotency_key"})
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class EnterpriseKnowledgeOrchestrator:
    """Explicitly wired application service; never used as a production default."""

    available = True

    def __init__(
        self,
        content_store: ImmutableContentStore,
        ingestion_store: IngestionFactStore,
        release_store: ApplicationReleaseFactStore,
        publisher: ReleasePublisherPort,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.content_store = content_store
        self.ingestion_store = ingestion_store
        self.release_store = release_store
        self.publisher = publisher
        self.clock = clock

    @staticmethod
    def _context(context: EnterpriseRequestContext) -> None:
        if (
            context.tenant_id != "default"
            or not context.actor_id
            or not context.run_id
            or not context.trace_id
        ):
            raise EnterpriseKnowledgeUnavailable("enterprise_context_invalid")

    @staticmethod
    def _ingestion_contract(
        value: object,
        *,
        context: EnterpriseRequestContext,
        expected_id: str = "",
        require_action_trace: bool = False,
        expected_status: IngestionState | None = None,
    ) -> IngestionContract:
        try:
            contract = IngestionContract.model_validate(value)
        except ValidationError as exc:
            raise EnterpriseKnowledgeUnavailable(
                "enterprise_response_contract_invalid"
            ) from exc
        if contract.tenant_id != context.tenant_id:
            raise EnterpriseKnowledgeUnavailable("enterprise_response_tenant_mismatch")
        if expected_id and contract.ingestion_id != expected_id:
            raise EnterpriseKnowledgeUnavailable("enterprise_response_identity_mismatch")
        if expected_status is not None and contract.status is not expected_status:
            raise EnterpriseKnowledgeUnavailable("enterprise_response_state_mismatch")
        if require_action_trace and (
            contract.run_id != context.run_id or contract.trace_id != context.trace_id
        ):
            raise EnterpriseKnowledgeUnavailable("enterprise_response_trace_mismatch")
        return contract

    @staticmethod
    def _release_contract(
        value: object,
        *,
        context: EnterpriseRequestContext,
        expected_id: str = "",
        expected_status: ReleaseState | None = None,
        require_action_trace: bool = False,
    ) -> ReleaseContract:
        try:
            contract = ReleaseContract.model_validate(value)
        except ValidationError as exc:
            raise EnterpriseKnowledgeUnavailable(
                "enterprise_response_contract_invalid"
            ) from exc
        if contract.tenant_id != context.tenant_id:
            raise EnterpriseKnowledgeUnavailable("enterprise_response_tenant_mismatch")
        if expected_id and contract.release_id != expected_id:
            raise EnterpriseKnowledgeUnavailable("enterprise_response_identity_mismatch")
        if expected_status is not None and contract.status is not expected_status:
            raise EnterpriseKnowledgeUnavailable("enterprise_response_state_mismatch")
        if require_action_trace and (
            contract.run_id != context.run_id or contract.trace_id != context.trace_id
        ):
            raise EnterpriseKnowledgeUnavailable("enterprise_response_trace_mismatch")
        return contract

    def create_ingestion(
        self,
        *,
        context: EnterpriseRequestContext,
        request: IngestionCreateRequest,
        content: bytes,
    ) -> IngestionContract:
        self._context(context)
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != request.content_sha256 or len(content) != request.size_bytes:
            raise EnterpriseKnowledgeUnavailable("ingestion_content_descriptor_mismatch")
        try:
            existing = self.ingestion_store.find_idempotency(
                tenant_id=context.tenant_id,
                idempotency_key=request.idempotency_key,
            )
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("ingestion_fact_read_failed") from exc
        if existing is not None:
            if not isinstance(existing, IngestionIdempotencyFact):
                raise EnterpriseKnowledgeUnavailable("ingestion_idempotency_fact_invalid")
            if existing.idempotency_key != request.idempotency_key:
                raise EnterpriseKnowledgeUnavailable("ingestion_idempotency_fact_invalid")
            if existing.content_sha256 != actual_hash:
                raise EnterpriseKnowledgeConflict("ingestion_idempotency_hash_conflict")
            return self._ingestion_contract(
                existing.contract,
                context=context,
                expected_status=IngestionState.DRAFT,
            )
        try:
            stored = self.content_store.put_immutable(
                tenant_id=context.tenant_id,
                content_sha256=actual_hash,
                content=content,
            )
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("immutable_content_write_failed") from exc
        if not isinstance(stored, StoredContent) or (
            stored.tenant_id != context.tenant_id
            or stored.content_sha256 != actual_hash
            or stored.size_bytes != len(content)
            or not stored.content_id
        ):
            raise EnterpriseKnowledgeUnavailable("immutable_content_contract_invalid")
        try:
            fact = self.ingestion_store.create_draft_atomic(
                context=context,
                request=request,
                stored_content=stored,
                now=self.clock(),
            )
        except EnterpriseKnowledgeConflict:
            raise
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("ingestion_draft_write_failed") from exc
        if not isinstance(fact, IngestionIdempotencyFact) or (
            fact.content_sha256 != actual_hash
            or fact.idempotency_key != request.idempotency_key
        ):
            raise EnterpriseKnowledgeUnavailable("ingestion_idempotency_fact_invalid")
        contract = self._ingestion_contract(
            fact.contract,
            context=context,
            expected_status=IngestionState.DRAFT,
            require_action_trace=True,
        )
        if contract.source_id != stored.content_id:
            raise EnterpriseKnowledgeUnavailable("ingestion_content_fact_mismatch")
        return contract

    def get_ingestion(
        self, *, context: EnterpriseRequestContext, ingestion_id: str
    ) -> IngestionContract:
        self._context(context)
        try:
            value = self.ingestion_store.get_ingestion(
                tenant_id=context.tenant_id, ingestion_id=ingestion_id
            )
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("ingestion_fact_read_failed") from exc
        if value is None:
            raise EnterpriseKnowledgeUnavailable("ingestion_not_found")
        return self._ingestion_contract(value, context=context, expected_id=ingestion_id)

    def list_releases(
        self, *, context: EnterpriseRequestContext
    ) -> list[ReleaseContract]:
        self._context(context)
        try:
            values = self.release_store.list_releases(tenant_id=context.tenant_id)
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("release_fact_read_failed") from exc
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise EnterpriseKnowledgeUnavailable("enterprise_response_contract_invalid")
        return [self._release_contract(value, context=context) for value in values]

    def create_release(
        self,
        *,
        context: EnterpriseRequestContext,
        request: ReleaseCreateRequest,
    ) -> ReleaseContract:
        self._context(context)
        request_hash = _request_sha256(request)
        try:
            existing = self.release_store.find_idempotency(
                tenant_id=context.tenant_id,
                idempotency_key=request.idempotency_key,
            )
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("release_fact_read_failed") from exc
        if existing is not None:
            if not isinstance(existing, ReleaseIdempotencyFact):
                raise EnterpriseKnowledgeUnavailable("release_idempotency_fact_invalid")
            if existing.idempotency_key != request.idempotency_key:
                raise EnterpriseKnowledgeUnavailable("release_idempotency_fact_invalid")
            if existing.request_sha256 != request_hash:
                raise EnterpriseKnowledgeConflict("release_idempotency_hash_conflict")
            return self._release_contract(
                existing.contract,
                context=context,
                expected_id=request.release_id,
                expected_status=ReleaseState.CANDIDATE,
            )
        try:
            fact = self.release_store.create_candidate_atomic(
                context=context,
                request=request,
                request_sha256=request_hash,
                now=self.clock(),
            )
        except EnterpriseKnowledgeConflict:
            raise
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("release_candidate_write_failed") from exc
        if not isinstance(fact, ReleaseIdempotencyFact) or (
            fact.idempotency_key != request.idempotency_key
            or fact.request_sha256 != request_hash
        ):
            raise EnterpriseKnowledgeUnavailable("release_idempotency_fact_invalid")
        contract = self._release_contract(
            fact.contract,
            context=context,
            expected_id=request.release_id,
            expected_status=ReleaseState.CANDIDATE,
            require_action_trace=True,
        )
        if (
            contract.manifest_sha256 != request.candidate_manifest_sha256
            or contract.embedding_profile != request.embedding_profile
        ):
            raise EnterpriseKnowledgeUnavailable("release_candidate_fact_mismatch")
        return contract

    def validate_release(
        self, *, context: EnterpriseRequestContext, release_id: str
    ) -> ReleaseContract:
        return self._release_action("validate", ReleaseState.VALIDATED, context, release_id)

    def publish_release(
        self, *, context: EnterpriseRequestContext, release_id: str
    ) -> ReleaseContract:
        return self._release_action("publish", ReleaseState.PUBLISHED, context, release_id)

    def rollback_release(
        self, *, context: EnterpriseRequestContext, release_id: str
    ) -> ReleaseContract:
        return self._release_action("rollback", ReleaseState.ROLLED_BACK, context, release_id)

    def _release_action(
        self,
        action: str,
        expected_status: ReleaseState,
        context: EnterpriseRequestContext,
        release_id: str,
    ) -> ReleaseContract:
        self._context(context)
        method = getattr(self.publisher, action)
        try:
            value = method(context=context, release_id=release_id)
        except EnterpriseKnowledgeConflict:
            raise
        except EnterpriseKnowledgeUnavailable:
            raise
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable(f"release_{action}_failed") from exc
        return self._release_contract(
            value,
            context=context,
            expected_id=release_id,
            expected_status=expected_status,
            require_action_trace=True,
        )

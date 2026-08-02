from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest

from backend.app.knowledge_enterprise_contracts import (
    AccessPolicyContract,
    EmbeddingProfileContract,
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
    get_enterprise_knowledge_application,
)
from backend.app.services.rag_enterprise_application import (
    EnterpriseKnowledgeOrchestrator,
    IngestionIdempotencyFact,
    ReleaseIdempotencyFact,
    StoredContent,
)


NOW = datetime(2026, 7, 31, 8, 0, tzinfo=timezone.utc)
CONTENT = b"enterprise-rag-content"


def _context(
    *, tenant_id: str = "default", run_id: str = "run-1", trace_id: str = "trace-1"
) -> EnterpriseRequestContext:
    return EnterpriseRequestContext(
        tenant_id=tenant_id, actor_id="reviewer-1", run_id=run_id, trace_id=trace_id
    )


def _ingestion_request(
    content: bytes = CONTENT, *, key: str = "ingestion-key-1"
) -> IngestionCreateRequest:
    return IngestionCreateRequest(
        filename="guide.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=len(content),
        content_sha256=hashlib.sha256(content).hexdigest(),
        idempotency_key=key,
        acl=AccessPolicyContract(visibility="tenant"),
    )


def _profile() -> EmbeddingProfileContract:
    return EmbeddingProfileContract(
        provider="sentence_transformers",
        model="BAAI/bge-large-zh-v1.5",
        version="1.5",
        dimension=1024,
        sparse_profile="bm25-zh-v1",
    )


def _release_request(
    *, key: str = "release-key-1", manifest: str = "a" * 64
) -> ReleaseCreateRequest:
    return ReleaseCreateRequest(
        release_id="RAG-R1",
        source_ledger_sha256="b" * 64,
        candidate_manifest_sha256=manifest,
        embedding_profile=_profile(),
        idempotency_key=key,
    )


class FakeContentStore:
    def __init__(self, events: list[str]):
        self.events = events
        self.writes = 0
        self.fail = False
        self.bad_contract = False

    def put_immutable(
        self, *, tenant_id: str, content_sha256: str, content: bytes
    ) -> StoredContent:
        self.events.append("content")
        self.writes += 1
        if self.fail:
            raise RuntimeError("injected_content_failure")
        return StoredContent(
            tenant_id="other" if self.bad_contract else tenant_id,
            content_id=f"content-{content_sha256[:12]}",
            content_sha256=content_sha256,
            size_bytes=len(content),
        )


class FakeIngestionStore:
    def __init__(self, events: list[str]):
        self.events = events
        self.by_key: dict[tuple[str, str], IngestionIdempotencyFact] = {}
        self.by_id: dict[tuple[str, str], IngestionContract] = {}
        self.writes = 0
        self.reads = 0
        self.fail_create = False
        self.bad_contract = False

    def find_idempotency(
        self, *, tenant_id: str, idempotency_key: str
    ) -> IngestionIdempotencyFact | None:
        self.reads += 1
        return self.by_key.get((tenant_id, idempotency_key))

    def create_draft_atomic(
        self, *, context, request, stored_content, now
    ) -> IngestionIdempotencyFact:
        self.events.append("draft")
        self.writes += 1
        if self.fail_create:
            raise RuntimeError("injected_fact_failure")
        key = (context.tenant_id, request.idempotency_key)
        existing = self.by_key.get(key)
        if existing is not None:
            if existing.content_sha256 != request.content_sha256:
                raise EnterpriseKnowledgeConflict("ingestion_idempotency_hash_conflict")
            return existing
        ingestion_id = f"ing-{request.content_sha256[:12]}"
        contract = IngestionContract(
            ingestion_id=ingestion_id,
            tenant_id="default",
            status=IngestionState.PARSING if self.bad_contract else IngestionState.DRAFT,
            source_id=stored_content.content_id,
            run_id=context.run_id,
            trace_id=context.trace_id,
            created_at=now,
            updated_at=now,
        )
        fact = IngestionIdempotencyFact(
            idempotency_key=request.idempotency_key,
            content_sha256=request.content_sha256,
            contract=contract,
        )
        self.by_key[key] = fact
        self.by_id[(context.tenant_id, ingestion_id)] = contract
        return fact

    def get_ingestion(
        self, *, tenant_id: str, ingestion_id: str
    ) -> IngestionContract | None:
        self.reads += 1
        return self.by_id.get((tenant_id, ingestion_id))


class FakeReleaseStore:
    def __init__(self, events: list[str]):
        self.events = events
        self.by_key: dict[tuple[str, str], ReleaseIdempotencyFact] = {}
        self.by_id: dict[tuple[str, str], ReleaseContract] = {}
        self.writes = 0
        self.reads = 0

    def find_idempotency(
        self, *, tenant_id: str, idempotency_key: str
    ) -> ReleaseIdempotencyFact | None:
        self.reads += 1
        return self.by_key.get((tenant_id, idempotency_key))

    def create_candidate_atomic(
        self, *, context, request, request_sha256, now
    ) -> ReleaseIdempotencyFact:
        self.events.append("candidate")
        self.writes += 1
        key = (context.tenant_id, request.idempotency_key)
        existing = self.by_key.get(key)
        if existing is not None:
            if existing.request_sha256 != request_sha256:
                raise EnterpriseKnowledgeConflict("release_idempotency_hash_conflict")
            return existing
        contract = ReleaseContract(
            release_id=request.release_id,
            tenant_id="default",
            status=ReleaseState.CANDIDATE,
            collection=f"rag_chunks_{request.release_id}",
            alias="rag_chunks_current",
            manifest_sha256=request.candidate_manifest_sha256,
            embedding_profile=request.embedding_profile,
            run_id=context.run_id,
            trace_id=context.trace_id,
            created_at=now,
            updated_at=now,
        )
        fact = ReleaseIdempotencyFact(
            idempotency_key=request.idempotency_key,
            request_sha256=request_sha256,
            contract=contract,
        )
        self.by_key[key] = fact
        self.by_id[(context.tenant_id, request.release_id)] = contract
        return fact

    def get_release(
        self, *, tenant_id: str, release_id: str
    ) -> ReleaseContract | None:
        self.reads += 1
        return self.by_id.get((tenant_id, release_id))

    def list_releases(self, *, tenant_id: str) -> list[ReleaseContract]:
        self.reads += 1
        return [value for (tenant, _), value in self.by_id.items() if tenant == tenant_id]


class FakePublisher:
    _TRANSITIONS = {
        "validate": (ReleaseState.CANDIDATE, ReleaseState.VALIDATED),
        "publish": (ReleaseState.VALIDATED, ReleaseState.PUBLISHED),
        "rollback": (ReleaseState.PUBLISHED, ReleaseState.ROLLED_BACK),
    }

    def __init__(self, store: FakeReleaseStore):
        self.store = store
        self.calls: list[str] = []
        self.fail_action = ""
        self.abnormal_action = ""

    def _act(self, action: str, *, context, release_id: str) -> object:
        self.calls.append(action)
        if action == self.fail_action:
            raise RuntimeError("injected_publish_failure")
        current = self.store.by_id.get((context.tenant_id, release_id))
        if current is None:
            raise EnterpriseKnowledgeUnavailable("release_not_found")
        expected, target = self._TRANSITIONS[action]
        if current.status is not expected:
            raise EnterpriseKnowledgeConflict(f"release_{action}_state_conflict")
        updated = current.model_copy(
            update={
                "status": target,
                "run_id": context.run_id,
                "trace_id": context.trace_id,
                "updated_at": NOW,
            }
        )
        if action == self.abnormal_action:
            return {"release_id": release_id, "status": target.value}
        self.store.by_id[(context.tenant_id, release_id)] = updated
        return updated

    def validate(self, *, context, release_id: str) -> object:
        return self._act("validate", context=context, release_id=release_id)

    def publish(self, *, context, release_id: str) -> object:
        return self._act("publish", context=context, release_id=release_id)

    def rollback(self, *, context, release_id: str) -> object:
        return self._act("rollback", context=context, release_id=release_id)


@pytest.fixture
def wired():
    events: list[str] = []
    content = FakeContentStore(events)
    ingestions = FakeIngestionStore(events)
    releases = FakeReleaseStore(events)
    publisher = FakePublisher(releases)
    app = EnterpriseKnowledgeOrchestrator(
        content, ingestions, releases, publisher, clock=lambda: NOW
    )
    return app, content, ingestions, releases, publisher, events


def test_ingestion_content_precedes_atomic_fact_and_retry_is_idempotent(wired):
    app, content, ingestions, _, _, events = wired
    request = _ingestion_request()

    first = app.create_ingestion(context=_context(), request=request, content=CONTENT)
    second = app.create_ingestion(context=_context(), request=request, content=CONTENT)

    assert first == second
    assert first.status is IngestionState.DRAFT
    assert events == ["content", "draft"]
    assert (content.writes, ingestions.writes) == (1, 1)


def test_ingestion_same_key_different_hash_conflicts_before_content_write(wired):
    app, content, _, _, _, _ = wired
    app.create_ingestion(
        context=_context(), request=_ingestion_request(), content=CONTENT
    )
    changed = b"different-content"

    with pytest.raises(EnterpriseKnowledgeConflict, match="hash_conflict"):
        app.create_ingestion(
            context=_context(),
            request=_ingestion_request(changed),
            content=changed,
        )

    assert content.writes == 1


@pytest.mark.parametrize(
    ("failure", "reason", "fact_writes"),
    [
        ("content", "immutable_content_write_failed", 0),
        ("fact", "ingestion_draft_write_failed", 1),
    ],
)
def test_ingestion_failure_injection_never_returns_a_draft(
    wired, failure, reason, fact_writes
):
    app, content, ingestions, _, _, events = wired
    content.fail = failure == "content"
    ingestions.fail_create = failure == "fact"

    with pytest.raises(EnterpriseKnowledgeUnavailable, match=reason):
        app.create_ingestion(
            context=_context(), request=_ingestion_request(), content=CONTENT
        )

    assert ingestions.writes == fact_writes
    assert not ingestions.by_id
    assert events == (["content"] if failure == "content" else ["content", "draft"])


def test_ingestion_rejects_cross_tenant_and_abnormal_store_contracts(wired):
    app, content, ingestions, _, _, events = wired
    with pytest.raises(EnterpriseKnowledgeUnavailable, match="context_invalid"):
        app.create_ingestion(
            context=_context(tenant_id="other"),
            request=_ingestion_request(),
            content=CONTENT,
        )
    assert events == []

    content.bad_contract = True
    with pytest.raises(EnterpriseKnowledgeUnavailable, match="content_contract_invalid"):
        app.create_ingestion(
            context=_context(), request=_ingestion_request(), content=CONTENT
        )
    content.bad_contract = False
    ingestions.bad_contract = True
    with pytest.raises(EnterpriseKnowledgeUnavailable, match="response_state_mismatch"):
        app.create_ingestion(
            context=_context(), request=_ingestion_request(key="ingestion-key-2"), content=CONTENT
        )


def test_ingestion_status_and_release_list_are_read_only(wired):
    app, _, ingestions, releases, _, _ = wired
    ingestion = app.create_ingestion(
        context=_context(), request=_ingestion_request(), content=CONTENT
    )
    app.create_release(context=_context(), request=_release_request())
    before = (ingestions.writes, releases.writes)

    assert app.get_ingestion(
        context=_context(), ingestion_id=ingestion.ingestion_id
    ) == ingestion
    assert [item.release_id for item in app.list_releases(context=_context())] == [
        "RAG-R1"
    ]
    assert (ingestions.writes, releases.writes) == before


def test_release_create_is_idempotent_and_conflicts_on_request_hash(wired):
    app, _, _, releases, _, events = wired
    request = _release_request()

    first = app.create_release(context=_context(), request=request)
    second = app.create_release(context=_context(), request=request)

    assert first == second
    assert first.status is ReleaseState.CANDIDATE
    assert releases.writes == 1
    assert events == ["candidate"]
    with pytest.raises(EnterpriseKnowledgeConflict, match="hash_conflict"):
        app.create_release(
            context=_context(), request=_release_request(manifest="c" * 64)
        )


def test_release_lifecycle_enforces_state_and_action_trace(wired):
    app, _, _, _, publisher, _ = wired
    app.create_release(context=_context(), request=_release_request())

    validated = app.validate_release(
        context=_context(run_id="run-2", trace_id="trace-2"), release_id="RAG-R1"
    )
    published = app.publish_release(
        context=_context(run_id="run-3", trace_id="trace-3"), release_id="RAG-R1"
    )
    rolled_back = app.rollback_release(
        context=_context(run_id="run-4", trace_id="trace-4"), release_id="RAG-R1"
    )

    assert [validated.status, published.status, rolled_back.status] == [
        ReleaseState.VALIDATED,
        ReleaseState.PUBLISHED,
        ReleaseState.ROLLED_BACK,
    ]
    assert (validated.trace_id, published.trace_id, rolled_back.trace_id) == (
        "trace-2",
        "trace-3",
        "trace-4",
    )
    assert publisher.calls == ["validate", "publish", "rollback"]


def test_release_publish_failure_and_abnormal_dto_fail_closed(wired):
    app, _, _, releases, publisher, _ = wired
    app.create_release(context=_context(), request=_release_request())
    app.validate_release(context=_context(), release_id="RAG-R1")
    publisher.fail_action = "publish"
    with pytest.raises(EnterpriseKnowledgeUnavailable, match="release_publish_failed"):
        app.publish_release(context=_context(), release_id="RAG-R1")
    assert releases.by_id[("default", "RAG-R1")].status is ReleaseState.VALIDATED

    publisher.fail_action = ""
    publisher.abnormal_action = "publish"
    with pytest.raises(
        EnterpriseKnowledgeUnavailable, match="enterprise_response_contract_invalid"
    ):
        app.publish_release(context=_context(), release_id="RAG-R1")


def test_default_production_dependency_remains_unavailable():
    application = get_enterprise_knowledge_application()

    assert application.available is False
    assert not isinstance(application, EnterpriseKnowledgeOrchestrator)

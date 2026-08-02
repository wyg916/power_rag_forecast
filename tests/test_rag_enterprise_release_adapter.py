from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from backend.app.knowledge_enterprise_contracts import (
    EmbeddingProfileContract,
    ReleaseContract,
    ReleaseState,
)
from backend.app.services.knowledge_enterprise_service import (
    EnterpriseKnowledgeConflict,
    EnterpriseKnowledgeUnavailable,
    EnterpriseRequestContext,
    get_enterprise_knowledge_application,
)
from backend.app.services.rag_release_application_adapter import (
    StrictReleasePublisherAdapter,
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


NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def _context(
    *, tenant: str = "default", run: str = "run-1", trace: str = "trace-1"
) -> EnterpriseRequestContext:
    return EnterpriseRequestContext(tenant, "reviewer-1", run, trace)


def _profile() -> ReleaseEmbeddingProfile:
    return ReleaseEmbeddingProfile(
        "sentence_transformers",
        "BAAI/bge-large-zh-v1.5",
        "bge-v1",
        1024,
        "bm25-zh-v1",
    )


def _gates() -> tuple[GateResult, ...]:
    return tuple(GateResult(name, True) for name in sorted(REQUIRED_RELEASE_GATES))


def _record(
    release_id: str, status: ReleaseStatus, *, previous: str = ""
) -> ReleaseRecord:
    return ReleaseRecord(
        tenant_id="default",
        release_id=release_id,
        status=status,
        collection=f"rag_chunks_{release_id}",
        alias=CURRENT_ALIAS,
        embedding_profile=_profile(),
        gates=_gates(),
        snapshot_id=f"snap-{release_id.lower()}",
        previous_release_id=previous,
        manifest_sha256="a" * 64,
    )


def _seed(record: ReleaseRecord) -> ReleaseContract:
    return ReleaseContract(
        release_id=record.release_id,
        tenant_id="default",
        status=ReleaseState.CANDIDATE,
        collection=record.collection,
        alias=CURRENT_ALIAS,
        manifest_sha256="a" * 64,
        embedding_profile=EmbeddingProfileContract(
            provider="sentence_transformers",
            model="BAAI/bge-large-zh-v1.5",
            version="bge-v1",
            dimension=1024,
            sparse_profile="bm25-zh-v1",
        ),
        run_id="run-create",
        trace_id="trace-create",
        created_at=NOW,
        updated_at=NOW,
    )


def _inspection(record: ReleaseRecord) -> CollectionInspection:
    return CollectionInspection(
        collection=record.collection,
        point_count=83,
        strict_mode_enabled=True,
        embedding_profile=record.embedding_profile,
        payload_embedding_profiles=(record.embedding_profile,),
        payload_release_ids=frozenset({record.release_id}),
        payload_tenant_ids=frozenset({record.tenant_id}),
        payload_statuses=frozenset({"published"}),
    )


class FakeControlPlane:
    def __init__(self, candidate: ReleaseRecord, previous: ReleaseRecord):
        self.inspections = {candidate.collection: _inspection(candidate)}
        self.snapshots = {(candidate.collection, candidate.snapshot_id)}
        self.alias = previous.collection
        self.switches = 0
        self.smoke_fail: set[str] = set()
        self.drift_after_smoke = False

    def inspect_collection(self, collection: str) -> CollectionInspection:
        return self.inspections[collection]

    def snapshot_exists(self, collection: str, snapshot_id: str) -> bool:
        return (collection, snapshot_id) in self.snapshots

    def current_alias(self, alias: str) -> str | None:
        assert alias == CURRENT_ALIAS
        return self.alias

    def switch_alias(
        self, alias: str, collection: str | None, *, expected_collection: str | None
    ) -> None:
        assert alias == CURRENT_ALIAS
        if self.alias != expected_collection:
            raise RuntimeError("alias_compare_and_swap_failed")
        self.alias = collection
        self.switches += 1

    def smoke(self, alias: str, release_id: str, collection: str) -> bool:
        ok = (
            alias == CURRENT_ALIAS
            and release_id not in self.smoke_fail
            and self.alias == collection
        )
        if ok and self.drift_after_smoke:
            self.alias = "rag_chunks_RAG-R1"
            self.drift_after_smoke = False
        return ok


class FakeFactStore:
    def __init__(self, candidate: ReleaseRecord, previous: ReleaseRecord):
        self.records = {
            ("default", candidate.release_id): candidate,
            ("default", previous.release_id): previous,
        }
        self.current = previous.release_id
        self.facts: list[ReleaseFact] = []
        self.manifests: list[AliasManifest] = []
        self.set_current_calls = 0
        self.fail_set_current_calls: set[int] = set()
        self.fail_trace_append = False
        self.missing_events: set[str] = set()
        self.alias_overrides: dict[str, str] = {}
        self.corrupt_trace_details = False
        self.get_calls = 0
        self.cross_tenant_on_get = 0

    def get_release(self, tenant_id: str, release_id: str) -> ReleaseRecord | None:
        self.get_calls += 1
        record = self.records.get((tenant_id, release_id))
        if record and self.get_calls == self.cross_tenant_on_get:
            return replace(record, tenant_id="other")
        return record

    def update_release(
        self, record: ReleaseRecord, *, expected_status: ReleaseStatus
    ) -> None:
        current = self.records[(record.tenant_id, record.release_id)]
        if current.status is not expected_status:
            raise RuntimeError("release_compare_and_swap_failed")
        self.records[(record.tenant_id, record.release_id)] = record

    def current_release_id(self, tenant_id: str) -> str | None:
        return self.current if tenant_id == "default" else None

    def set_current_release(
        self, tenant_id: str, release_id: str | None, *, expected_previous: str | None
    ) -> None:
        self.set_current_calls += 1
        if self.set_current_calls in self.fail_set_current_calls:
            raise RuntimeError("injected_postgres_failure")
        if tenant_id != "default" or self.current != expected_previous:
            raise RuntimeError("current_release_compare_and_swap_failed")
        self.current = release_id

    def finalize_publish(
        self, published: ReleaseRecord, *, previous_release_id: str | None
    ) -> None:
        previous = self.records[("default", previous_release_id)]
        self.records[("default", published.release_id)] = published
        self.records[("default", previous.release_id)] = replace(
            previous, status=ReleaseStatus.SUPERSEDED
        )

    def finalize_rollback(
        self, rolled_back: ReleaseRecord, *, previous_release_id: str
    ) -> None:
        previous = self.records[("default", previous_release_id)]
        self.records[("default", rolled_back.release_id)] = rolled_back
        self.records[("default", previous.release_id)] = replace(
            previous, status=ReleaseStatus.PUBLISHED
        )

    def save_alias_manifest(self, manifest: AliasManifest) -> None:
        self.manifests.append(manifest)

    def append_fact(self, fact: ReleaseFact) -> None:
        if self.fail_trace_append and fact.event.startswith("enterprise_"):
            raise RuntimeError("injected_trace_fact_failure")
        self.facts.append(fact)

    def latest_fact(
        self, tenant_id: str, release_id: str, event: str
    ) -> ReleaseFact | None:
        if event in self.missing_events:
            return None
        fact = next(
            (
                fact
                for fact in reversed(self.facts)
                if fact.tenant_id == tenant_id
                and fact.release_id == release_id
                and fact.event == event
            ),
            None,
        )
        if fact and event in self.alias_overrides:
            fact = replace(
                fact,
                details=dict(fact.details or {}, alias_after=self.alias_overrides[event]),
            )
        if fact and self.corrupt_trace_details and event.startswith("enterprise_"):
            fact = replace(fact, details=7)  # type: ignore[arg-type]
        return fact


class FakeCache:
    def __init__(self):
        self.invalidated: list[tuple[str, str]] = []

    def invalidate_release(self, tenant_id: str, release_id: str) -> None:
        self.invalidated.append((tenant_id, release_id))


class FakeContractSource:
    def __init__(self, contract: ReleaseContract):
        self.contract = contract

    def get_release(
        self, *, tenant_id: str, release_id: str
    ) -> ReleaseContract | None:
        if tenant_id != self.contract.tenant_id or release_id != self.contract.release_id:
            return None
        return self.contract


class StepClock:
    def __init__(self, *values: float):
        self.values = iter(values)

    def __call__(self) -> float:
        return next(self.values)


class FixedRuntime:
    def __init__(self, operation: ReleaseOperation):
        self.operation = operation

    def validate(self, tenant_id: str, release_id: str) -> ReleaseOperation:
        return self.operation

    publish = validate
    rollback = validate


def _setup():
    previous = _record("RAG-R1", ReleaseStatus.PUBLISHED)
    candidate = _record("RAG-R2", ReleaseStatus.CANDIDATE)
    control = FakeControlPlane(candidate, previous)
    facts = FakeFactStore(candidate, previous)
    cache = FakeCache()
    service = ReleasePublisher(control, facts, cache, _profile())
    contracts = FakeContractSource(_seed(candidate))
    adapter = StrictReleasePublisherAdapter(
        service, facts, contracts, control, clock=lambda: NOW
    )
    return adapter, service, control, facts, cache, contracts


def _validated():
    setup = _setup()
    setup[0].validate(context=_context(), release_id="RAG-R2")
    return setup


def test_publish_maps_verified_rt4_operation_record_and_facts_to_m5_contract():
    adapter, _, control, facts, _, _ = _validated()

    result = adapter.publish(
        context=_context(run="run-publish", trace="trace-publish"),
        release_id="RAG-R2",
    )

    assert result.status is ReleaseState.PUBLISHED
    assert (result.run_id, result.trace_id) == ("run-publish", "trace-publish")
    assert result.manifest_sha256 == "a" * 64
    assert facts.current == "RAG-R2" and control.alias == "rag_chunks_RAG-R2"
    trace_fact = facts.latest_fact("default", "RAG-R2", "enterprise_publish_completed")
    assert trace_fact is not None and trace_fact.details["trace_id"] == "trace-publish"


def test_publish_postgres_failure_rolls_alias_back_and_is_unavailable():
    adapter, _, control, facts, _, _ = _validated()
    facts.fail_set_current_calls = {1}

    with pytest.raises(EnterpriseKnowledgeUnavailable, match="postgres_current_failed"):
        adapter.publish(context=_context(), release_id="RAG-R2")

    assert control.alias == "rag_chunks_RAG-R1" and facts.current == "RAG-R1"
    assert facts.records[("default", "RAG-R2")].status is ReleaseStatus.VALIDATED
    assert facts.latest_fact("default", "RAG-R2", "enterprise_publish_completed") is None


def test_publish_smoke_failure_restores_both_sides_and_is_unavailable():
    adapter, _, control, facts, _, _ = _validated()
    control.smoke_fail = {"RAG-R2"}

    with pytest.raises(EnterpriseKnowledgeUnavailable, match="post_switch_smoke_failed"):
        adapter.publish(context=_context(), release_id="RAG-R2")

    assert control.alias == "rag_chunks_RAG-R1" and facts.current == "RAG-R1"
    assert facts.records[("default", "RAG-R2")].status is ReleaseStatus.VALIDATED


def test_publish_retry_is_idempotent_but_binds_the_new_trace():
    adapter, _, control, facts, _, _ = _validated()
    adapter.publish(context=_context(), release_id="RAG-R2")
    before = (control.switches, facts.set_current_calls)

    retried = adapter.publish(
        context=_context(run="run-retry", trace="trace-retry"), release_id="RAG-R2"
    )

    assert retried.status is ReleaseState.PUBLISHED
    assert retried.trace_id == "trace-retry"
    assert (control.switches, facts.set_current_calls) == before
    completed = [f for f in facts.facts if f.event == "enterprise_publish_completed"]
    assert len(completed) == 2 and completed[-1].details["idempotent"] is True


def test_known_release_state_conflict_is_not_collapsed_to_unavailable():
    adapter, _, _, _, _, _ = _setup()

    with pytest.raises(EnterpriseKnowledgeConflict, match="release_validation_required"):
        adapter.publish(context=_context(), release_id="RAG-R2")


def test_unknown_runtime_reason_is_normalized_without_leaking_details():
    adapter, _, _, _, _, _ = _setup()
    adapter.service = FixedRuntime(
        ReleaseOperation(
            False, "secret_backend_detail", ReleaseStatus.CANDIDATE, False, 1, True
        )
    )

    with pytest.raises(EnterpriseKnowledgeUnavailable) as caught:
        adapter.validate(context=_context(), release_id="RAG-R2")

    assert str(caught.value) == "release_validate_failed:unknown"
    assert "secret_backend_detail" not in str(caught.value)


def test_release_identifier_is_rejected_before_runtime_or_fact_access():
    adapter, _, _, facts, _, _ = _setup()

    with pytest.raises(EnterpriseKnowledgeUnavailable, match="context_invalid"):
        adapter.validate(context=_context(), release_id="bad/id")

    assert facts.get_calls == 0 and facts.facts == []


@pytest.mark.parametrize("tamper", ["manifest", "passed_gate_reason"])
def test_tampered_rt4_record_cannot_be_converted_to_m5(tamper: str):
    adapter, _, _, facts, _, _ = _setup()
    candidate = facts.records[("default", "RAG-R2")]
    if tamper == "manifest":
        candidate = replace(candidate, manifest_sha256="b" * 64)
    else:
        candidate = replace(
            candidate,
            gates=(replace(candidate.gates[0], reason="unexpected"),)
            + candidate.gates[1:],
        )
    facts.records[("default", "RAG-R2")] = candidate

    expected = "contract_mismatch" if tamper == "manifest" else "basic_gate_failed"
    with pytest.raises(EnterpriseKnowledgeUnavailable, match=expected):
        adapter.validate(context=_context(), release_id="RAG-R2")


def test_rollback_rto_failure_never_returns_a_rolled_back_contract():
    adapter, _, control, facts, cache, contracts = _validated()
    adapter.publish(context=_context(), release_id="RAG-R2")
    timed = ReleasePublisher(
        control, facts, cache, _profile(), clock=StepClock(0.0, 301.0)
    )
    timed_adapter = StrictReleasePublisherAdapter(
        timed, facts, contracts, control, clock=lambda: NOW
    )

    with pytest.raises(EnterpriseKnowledgeUnavailable, match="rollback_rto_failed"):
        timed_adapter.rollback(context=_context(), release_id="RAG-R2")

    assert facts.records[("default", "RAG-R2")].status is ReleaseStatus.ROLLED_BACK
    assert facts.latest_fact("default", "RAG-R2", "enterprise_rollback_completed") is None


def test_cross_tenant_record_and_missing_trace_fail_closed():
    adapter, _, _, facts, _, _ = _setup()
    with pytest.raises(EnterpriseKnowledgeUnavailable, match="context_invalid"):
        adapter.validate(context=_context(trace=""), release_id="RAG-R2")
    assert facts.records[("default", "RAG-R2")].status is ReleaseStatus.CANDIDATE

    facts.cross_tenant_on_get = 2
    with pytest.raises(EnterpriseKnowledgeUnavailable, match="record_identity_mismatch"):
        adapter.validate(context=_context(), release_id="RAG-R2")


@pytest.mark.parametrize("fault", ["operation_fact", "trace_fact"])
def test_fact_fault_after_publish_is_unavailable_and_never_fakes_success(fault: str):
    adapter, _, _, facts, _, _ = _validated()
    if fault == "operation_fact":
        facts.missing_events = {"published"}
    else:
        facts.fail_trace_append = True

    with pytest.raises(EnterpriseKnowledgeUnavailable, match="fact"):
        adapter.publish(context=_context(), release_id="RAG-R2")

    assert facts.records[("default", "RAG-R2")].status is ReleaseStatus.PUBLISHED
    assert facts.latest_fact("default", "RAG-R2", "enterprise_publish_completed") is None


def test_final_operation_fact_alias_must_match_the_published_collection():
    adapter, _, _, facts, _, _ = _validated()
    facts.alias_overrides["published"] = "rag_chunks_RAG-R1"

    with pytest.raises(EnterpriseKnowledgeUnavailable, match="fact_alias_mismatch"):
        adapter.publish(context=_context(), release_id="RAG-R2")


@pytest.mark.parametrize("fault", ["clock", "trace_details"])
def test_clock_and_trace_shape_failures_are_stable_unavailable(fault: str):
    adapter, service, control, facts, _, contracts = _validated()
    if fault == "clock":
        def broken_clock() -> datetime:
            raise RuntimeError("secret_clock_failure")

        adapter = StrictReleasePublisherAdapter(
            service, facts, contracts, control, clock=broken_clock
        )
        expected = "release_contract_conversion_failed"
    else:
        facts.corrupt_trace_details = True
        expected = "release_trace_fact_mismatch"

    with pytest.raises(EnterpriseKnowledgeUnavailable, match=expected) as caught:
        adapter.publish(context=_context(), release_id="RAG-R2")

    assert "secret_clock_failure" not in str(caught.value)


def test_final_alias_drift_after_successful_smoke_is_unavailable():
    adapter, _, control, facts, _, _ = _validated()
    control.drift_after_smoke = True

    with pytest.raises(EnterpriseKnowledgeUnavailable, match="alias_fact_mismatch"):
        adapter.publish(context=_context(), release_id="RAG-R2")

    assert facts.current == "RAG-R2"
    assert control.alias == "rag_chunks_RAG-R1"


def test_default_production_application_is_still_unavailable():
    assert get_enterprise_knowledge_application().available is False

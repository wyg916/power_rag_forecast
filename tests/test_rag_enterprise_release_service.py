from __future__ import annotations

from dataclasses import replace

import pytest

from backend.app.services.rag_release_service import (
    CURRENT_ALIAS,
    REQUIRED_RELEASE_GATES,
    AliasManifest,
    CollectionInspection,
    GateResult,
    ReleaseEmbeddingProfile,
    ReleasePublisher,
    ReleaseRecord,
    ReleaseStatus,
)


def _profile(version="bge-v1"):
    return ReleaseEmbeddingProfile(
        "sentence_transformers", "BAAI/bge-large-zh-v1.5", version, 1024, "bm25-zh-v1"
    )


def _gates():
    return tuple(GateResult(name, True) for name in sorted(REQUIRED_RELEASE_GATES))


def _release(release_id, status, *, previous=""):
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
    )


def _inspection(record, **changes):
    values = {
        "collection": record.collection,
        "point_count": 83,
        "embedding_profile": record.embedding_profile,
        "payload_embedding_profiles": (record.embedding_profile,),
        "payload_release_ids": frozenset({record.release_id}),
        "payload_tenant_ids": frozenset({record.tenant_id}),
        "payload_statuses": frozenset({"published"}),
    }
    values.update(changes)
    return CollectionInspection(**values)


class FakeQdrantAdmin:
    def __init__(self, candidate, previous):
        self.inspections = {candidate.collection: _inspection(candidate)}
        self.snapshots = {(candidate.collection, candidate.snapshot_id)}
        self.aliases = {CURRENT_ALIAS: previous.collection if previous else None}
        self.inspect_count = 0
        self.switch_count = 0
        self.switch_calls = []
        self.fail_switch_calls = set()
        self.smoke_fail_releases = set()
        self.deleted_collections = []
        self.events = []

    def inspect_collection(self, collection):
        self.inspect_count += 1
        return self.inspections[collection]

    def snapshot_exists(self, collection, snapshot_id):
        return (collection, snapshot_id) in self.snapshots

    def current_alias(self, alias):
        return self.aliases.get(alias)

    def switch_alias(self, alias, collection, *, expected_collection):
        self.switch_count += 1
        self.switch_calls.append((alias, collection, expected_collection))
        self.events.append(("alias", collection))
        if self.switch_count in self.fail_switch_calls:
            raise RuntimeError("injected alias failure")
        if self.aliases.get(alias) != expected_collection:
            raise RuntimeError("alias compare-and-swap failed")
        self.aliases[alias] = collection

    def smoke(self, alias, release_id, collection):
        return (
            release_id not in self.smoke_fail_releases
            and self.aliases.get(alias) == collection
        )


class FakeReleaseStore:
    def __init__(self, candidate, previous):
        self.records = {(candidate.tenant_id, candidate.release_id): candidate}
        if previous:
            self.records[(previous.tenant_id, previous.release_id)] = previous
        self.current = {"default": previous.release_id if previous else None}
        self.facts = []
        self.manifests: list[AliasManifest] = []
        self.set_current_count = 0
        self.fail_set_current_calls = set()
        self.events = []

    def get_release(self, tenant_id, release_id):
        return self.records.get((tenant_id, release_id))

    def update_release(self, record, *, expected_status):
        current = self.records[(record.tenant_id, record.release_id)]
        if current.status is not expected_status:
            raise RuntimeError("release compare-and-swap failed")
        self.records[(record.tenant_id, record.release_id)] = record

    def current_release_id(self, tenant_id):
        return self.current.get(tenant_id)

    def set_current_release(self, tenant_id, release_id, *, expected_previous):
        self.set_current_count += 1
        self.events.append(("postgres_current", release_id))
        if self.set_current_count in self.fail_set_current_calls:
            raise RuntimeError("injected postgres failure")
        if self.current.get(tenant_id) != expected_previous:
            raise RuntimeError("current release compare-and-swap failed")
        self.current[tenant_id] = release_id

    def save_alias_manifest(self, manifest):
        self.manifests.append(manifest)

    def append_fact(self, fact):
        self.facts.append(fact)


class FakeCache:
    def __init__(self):
        self.invalidated = []

    def invalidate_release(self, tenant_id, release_id):
        self.invalidated.append((tenant_id, release_id))


class StepClock:
    def __init__(self, *values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


def _setup():
    previous = _release("RAG-R1", ReleaseStatus.PUBLISHED)
    candidate = _release("RAG-R2", ReleaseStatus.CANDIDATE)
    qdrant = FakeQdrantAdmin(candidate, previous)
    store = FakeReleaseStore(candidate, previous)
    events = []
    qdrant.events = events
    store.events = events
    cache = FakeCache()
    return ReleasePublisher(qdrant, store, cache), qdrant, store, cache


def _validated():
    service, qdrant, store, cache = _setup()
    assert service.validate("default", "RAG-R2").succeeded is True
    return service, qdrant, store, cache


def test_validate_is_complete_and_idempotent_without_alias_mutation():
    service, qdrant, store, cache = _setup()
    first = service.validate("default", "RAG-R2")
    inspected = qdrant.inspect_count
    second = service.validate("default", "RAG-R2")

    assert first.succeeded is True and first.status is ReleaseStatus.VALIDATED
    assert second.succeeded is True and second.idempotent is True
    assert qdrant.inspect_count == inspected
    assert qdrant.switch_calls == [] and store.manifests == [] and cache.invalidated == []


def test_validate_rejects_incomplete_gate_payload_profile_and_snapshot():
    service, qdrant, store, _ = _setup()
    candidate = store.get_release("default", "RAG-R2")
    store.records[("default", "RAG-R2")] = replace(candidate, gates=candidate.gates[:-1])
    assert service.validate("default", "RAG-R2").reason == "release_gates_incomplete"

    service, qdrant, store, _ = _setup()
    qdrant.inspections["rag_chunks_RAG-R2"] = _inspection(
        store.get_release("default", "RAG-R2"),
        payload_release_ids=frozenset({"RAG-R1"}),
    )
    assert service.validate("default", "RAG-R2").reason == "payload_release_mismatch"

    service, qdrant, store, _ = _setup()
    qdrant.inspections["rag_chunks_RAG-R2"] = _inspection(
        store.get_release("default", "RAG-R2"),
        payload_embedding_profiles=(_profile("wrong"),),
    )
    assert service.validate("default", "RAG-R2").reason == "payload_embedding_profile_mismatch"

    service, qdrant, _, _ = _setup()
    qdrant.snapshots.clear()
    assert service.validate("default", "RAG-R2").reason == "snapshot_missing"


def test_publish_switches_alias_before_pg_saves_manifest_and_is_idempotent():
    service, qdrant, store, cache = _validated()
    first = service.publish("default", "RAG-R2")
    switch_count, current_count = qdrant.switch_count, store.set_current_count
    second = service.publish("default", "RAG-R2")

    assert first.succeeded is True and first.status is ReleaseStatus.PUBLISHED
    assert qdrant.switch_calls[0] == (CURRENT_ALIAS, "rag_chunks_RAG-R2", "rag_chunks_RAG-R1")
    assert qdrant.events[:2] == [("alias", "rag_chunks_RAG-R2"), ("postgres_current", "RAG-R2")]
    assert store.current["default"] == "RAG-R2"
    assert store.get_release("default", "RAG-R1").status is ReleaseStatus.SUPERSEDED
    manifest = store.manifests[0]
    assert manifest.before_collection == "rag_chunks_RAG-R1"
    assert manifest.after_collection == "rag_chunks_RAG-R2"
    assert manifest.snapshot_id == "snap-rag-r2" and manifest.snapshot_contains_alias is False
    assert set(cache.invalidated) == {("default", "RAG-R1"), ("default", "RAG-R2")}
    assert qdrant.deleted_collections == []
    assert second.succeeded is True and second.idempotent is True
    assert qdrant.switch_count == switch_count and store.set_current_count == current_count


def test_alias_failure_changes_no_current_fact():
    service, qdrant, store, cache = _validated()
    qdrant.fail_switch_calls = {1}
    result = service.publish("default", "RAG-R2")

    assert result.reason == "alias_switch_failed"
    assert qdrant.current_alias(CURRENT_ALIAS) == "rag_chunks_RAG-R1"
    assert store.current["default"] == "RAG-R1"
    assert store.get_release("default", "RAG-R2").status is ReleaseStatus.VALIDATED
    assert cache.invalidated == []


def test_pg_failure_immediately_restores_alias_and_preserves_candidate_fact():
    service, qdrant, store, cache = _validated()
    store.fail_set_current_calls = {1}
    result = service.publish("default", "RAG-R2")

    assert result.reason == "postgres_current_failed" and result.consistency_restored is True
    assert qdrant.current_alias(CURRENT_ALIAS) == "rag_chunks_RAG-R1"
    assert store.current["default"] == "RAG-R1"
    assert store.get_release("default", "RAG-R2").status is ReleaseStatus.VALIDATED
    assert store.facts[-1].event == "publish_failed"
    assert set(cache.invalidated) == {("default", "RAG-R1"), ("default", "RAG-R2")}


def test_pg_failure_records_alias_compensation_failure():
    service, qdrant, store, _ = _validated()
    store.fail_set_current_calls = {1}
    qdrant.fail_switch_calls = {2}
    result = service.publish("default", "RAG-R2")

    assert result.reason == "postgres_failed_alias_rollback_failed"
    assert result.consistency_restored is False
    assert qdrant.current_alias(CURRENT_ALIAS) == "rag_chunks_RAG-R2"
    assert store.current["default"] == "RAG-R1"
    assert store.facts[-1].reason == result.reason


def test_post_switch_smoke_failure_atomically_restores_alias_and_pg():
    service, qdrant, store, cache = _validated()
    qdrant.smoke_fail_releases = {"RAG-R2"}
    result = service.publish("default", "RAG-R2")

    assert result.reason == "post_switch_smoke_failed"
    assert result.consistency_restored is True
    assert qdrant.current_alias(CURRENT_ALIAS) == "rag_chunks_RAG-R1"
    assert store.current["default"] == "RAG-R1"
    assert store.get_release("default", "RAG-R2").status is ReleaseStatus.VALIDATED
    assert set(cache.invalidated) == {("default", "RAG-R1"), ("default", "RAG-R2")}


def test_rollback_is_atomic_idempotent_and_keeps_old_collection():
    service, qdrant, store, cache = _validated()
    assert service.publish("default", "RAG-R2").succeeded is True
    cache.invalidated.clear()
    first = service.rollback("default", "RAG-R2")
    switch_count, current_count = qdrant.switch_count, store.set_current_count
    second = service.rollback("default", "RAG-R2")

    assert first.succeeded is True and first.status is ReleaseStatus.ROLLED_BACK
    assert qdrant.current_alias(CURRENT_ALIAS) == "rag_chunks_RAG-R1"
    assert store.current["default"] == "RAG-R1"
    assert store.get_release("default", "RAG-R1").status is ReleaseStatus.PUBLISHED
    assert set(cache.invalidated) == {("default", "RAG-R1"), ("default", "RAG-R2")}
    assert qdrant.deleted_collections == []
    assert second.succeeded is True and second.idempotent is True
    assert qdrant.switch_count == switch_count and store.set_current_count == current_count


def test_rollback_alias_failure_preserves_published_state_and_failure_fact():
    service, qdrant, store, _ = _validated()
    assert service.publish("default", "RAG-R2").succeeded is True
    qdrant.fail_switch_calls = {qdrant.switch_count + 1}
    result = service.rollback("default", "RAG-R2")

    assert result.reason == "rollback_alias_failed"
    assert qdrant.current_alias(CURRENT_ALIAS) == "rag_chunks_RAG-R2"
    assert store.current["default"] == "RAG-R2"
    assert store.get_release("default", "RAG-R2").status is ReleaseStatus.PUBLISHED
    assert store.facts[-1].event == "rollback_failed"


def test_rollback_reports_five_minute_rto_protocol():
    service, qdrant, store, cache = _validated()
    assert service.publish("default", "RAG-R2").succeeded is True
    timed = ReleasePublisher(qdrant, store, cache, clock=StepClock(0.0, 301.0))

    result = timed.rollback("default", "RAG-R2")

    assert result.succeeded is True
    assert result.elapsed_ms == 301_000
    assert result.rto_met is False

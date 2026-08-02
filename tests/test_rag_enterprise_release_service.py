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


def _profile(version="bge-v1", sparse_profile="bm25-zh-v1"):
    return ReleaseEmbeddingProfile(
        "sentence_transformers", "BAAI/bge-large-zh-v1.5", version, 1024, sparse_profile
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
        manifest_sha256="a" * 64,
    )


def _inspection(record, **changes):
    values = {
        "collection": record.collection,
        "point_count": 83,
        "strict_mode_enabled": True,
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
        self.finalize_publish_count = 0
        self.finalize_rollback_count = 0
        self.fail_finalize_publish_calls = set()
        self.fail_finalize_rollback_calls = set()
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

    def finalize_publish(self, published, *, previous_release_id):
        self.finalize_publish_count += 1
        if self.finalize_publish_count in self.fail_finalize_publish_calls:
            raise RuntimeError("injected publish finalize failure")
        target = self.records[(published.tenant_id, published.release_id)]
        if target.status is not ReleaseStatus.VALIDATED:
            raise RuntimeError("publish finalize target state invalid")
        previous = None
        if previous_release_id:
            previous = self.records[(published.tenant_id, previous_release_id)]
            if previous.status is not ReleaseStatus.PUBLISHED:
                raise RuntimeError("publish finalize previous state invalid")
        updates = {(published.tenant_id, published.release_id): published}
        if previous is not None:
            updates[(previous.tenant_id, previous.release_id)] = replace(
                previous, status=ReleaseStatus.SUPERSEDED
            )
        self.records.update(updates)

    def finalize_rollback(self, rolled_back, *, previous_release_id):
        self.finalize_rollback_count += 1
        if self.finalize_rollback_count in self.fail_finalize_rollback_calls:
            raise RuntimeError("injected rollback finalize failure")
        target = self.records[(rolled_back.tenant_id, rolled_back.release_id)]
        if target.status is not ReleaseStatus.PUBLISHED:
            raise RuntimeError("rollback finalize target state invalid")
        updates = {(rolled_back.tenant_id, rolled_back.release_id): rolled_back}
        if previous_release_id:
            previous = self.records[(rolled_back.tenant_id, previous_release_id)]
            if previous.status is not ReleaseStatus.SUPERSEDED:
                raise RuntimeError("rollback finalize previous state invalid")
            updates[(previous.tenant_id, previous.release_id)] = replace(
                previous, status=ReleaseStatus.PUBLISHED
            )
        self.records.update(updates)


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
    return ReleasePublisher(qdrant, store, cache, _profile()), qdrant, store, cache


def _validated():
    service, qdrant, store, cache = _setup()
    assert service.validate("default", "RAG-R2").succeeded is True
    return service, qdrant, store, cache


def test_expected_profile_is_a_required_constructor_fact():
    _, qdrant, store, cache = _setup()
    with pytest.raises(TypeError):
        ReleasePublisher(qdrant, store, cache)  # type: ignore[call-arg]


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

    service, qdrant, store, _ = _setup()
    qdrant.inspections["rag_chunks_RAG-R2"] = _inspection(
        store.get_release("default", "RAG-R2"),
        strict_mode_enabled=False,
    )
    assert service.validate("default", "RAG-R2").reason == "collection_strict_mode_required"


def test_invalid_manifest_fails_before_control_plane_or_store_writes():
    service, qdrant, store, cache = _setup()
    candidate = store.get_release("default", "RAG-R2")
    store.records[("default", "RAG-R2")] = replace(candidate, manifest_sha256="")

    result = service.validate("default", "RAG-R2")

    assert result.reason == "release_manifest_invalid"
    assert qdrant.inspect_count == 0 and qdrant.switch_count == 0
    assert store.facts == [] and store.manifests == []
    assert store.get_release("default", "RAG-R2").status is ReleaseStatus.CANDIDATE
    assert cache.invalidated == []


@pytest.mark.parametrize(
    "drifted",
    (_profile("bge-v2"), _profile(sparse_profile="bm25-zh-v2")),
)
def test_candidate_version_or_sparse_profile_drift_is_fail_closed(drifted):
    service, _, store, _ = _setup()
    candidate = store.get_release("default", "RAG-R2")
    store.records[("default", "RAG-R2")] = replace(
        candidate, embedding_profile=drifted
    )

    result = service.validate("default", "RAG-R2")

    assert result.reason == "candidate_embedding_profile_mismatch"
    assert store.get_release("default", "RAG-R2").status is ReleaseStatus.CANDIDATE


@pytest.mark.parametrize(
    "drifted",
    (_profile("bge-v2"), _profile(sparse_profile="bm25-zh-v2")),
)
def test_collection_and_payload_profiles_must_equal_deployment_expected(drifted):
    service, qdrant, store, _ = _setup()
    candidate = store.get_release("default", "RAG-R2")
    qdrant.inspections[candidate.collection] = _inspection(
        candidate, embedding_profile=drifted
    )
    assert service.validate("default", "RAG-R2").reason == "collection_embedding_profile_mismatch"

    service, qdrant, store, _ = _setup()
    candidate = store.get_release("default", "RAG-R2")
    qdrant.inspections[candidate.collection] = _inspection(
        candidate, payload_embedding_profiles=(drifted,)
    )
    assert service.validate("default", "RAG-R2").reason == "payload_embedding_profile_mismatch"


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


def test_first_release_can_rollback_to_no_current_alias_and_is_idempotent():
    candidate = _release("RAG-R1", ReleaseStatus.CANDIDATE)
    qdrant = FakeQdrantAdmin(candidate, None)
    store = FakeReleaseStore(candidate, None)
    cache = FakeCache()
    service = ReleasePublisher(qdrant, store, cache, _profile())

    assert service.validate("default", "RAG-R1").succeeded is True
    assert service.publish("default", "RAG-R1").succeeded is True
    first = service.rollback("default", "RAG-R1")
    switch_count, current_count = qdrant.switch_count, store.set_current_count
    second = service.rollback("default", "RAG-R1")

    assert first.succeeded is True and first.status is ReleaseStatus.ROLLED_BACK
    assert qdrant.current_alias(CURRENT_ALIAS) is None
    assert store.current["default"] is None
    assert store.get_release("default", "RAG-R1").status is ReleaseStatus.ROLLED_BACK
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


def test_publish_finalize_failure_compensates_and_can_be_retried():
    service, qdrant, store, cache = _validated()
    store.fail_finalize_publish_calls = {1}

    failed = service.publish("default", "RAG-R2")

    assert failed.reason == "publish_finalize_failed"
    assert failed.consistency_restored is True
    assert qdrant.current_alias(CURRENT_ALIAS) == "rag_chunks_RAG-R1"
    assert store.current["default"] == "RAG-R1"
    assert store.get_release("default", "RAG-R2").status is ReleaseStatus.VALIDATED
    assert store.get_release("default", "RAG-R1").status is ReleaseStatus.PUBLISHED
    assert store.facts[-1].reason == "publish_finalize_failed"
    assert service.publish("default", "RAG-R2").succeeded is True


def test_publish_finalize_compensation_failure_is_explicit():
    service, qdrant, store, _ = _validated()
    store.fail_finalize_publish_calls = {1}
    qdrant.fail_switch_calls = {2}

    result = service.publish("default", "RAG-R2")

    assert result.reason == "publish_finalize_compensation_failed"
    assert result.consistency_restored is False
    assert store.get_release("default", "RAG-R2").status is ReleaseStatus.VALIDATED
    assert store.get_release("default", "RAG-R1").status is ReleaseStatus.PUBLISHED
    assert qdrant.current_alias(CURRENT_ALIAS) == "rag_chunks_RAG-R2"
    assert store.current["default"] == "RAG-R2"


def test_rollback_finalize_failure_compensates_and_can_be_retried():
    service, qdrant, store, cache = _validated()
    assert service.publish("default", "RAG-R2").succeeded is True
    store.fail_finalize_rollback_calls = {1}

    failed = service.rollback("default", "RAG-R2")

    assert failed.reason == "rollback_finalize_failed"
    assert failed.consistency_restored is True
    assert qdrant.current_alias(CURRENT_ALIAS) == "rag_chunks_RAG-R2"
    assert store.current["default"] == "RAG-R2"
    assert store.get_release("default", "RAG-R2").status is ReleaseStatus.PUBLISHED
    assert store.get_release("default", "RAG-R1").status is ReleaseStatus.SUPERSEDED
    assert store.facts[-1].reason == "rollback_finalize_failed"
    assert service.rollback("default", "RAG-R2").succeeded is True


def test_rollback_finalize_compensation_failure_is_explicit():
    service, qdrant, store, _ = _validated()
    assert service.publish("default", "RAG-R2").succeeded is True
    store.fail_finalize_rollback_calls = {1}
    qdrant.fail_switch_calls = {qdrant.switch_count + 2}

    result = service.rollback("default", "RAG-R2")

    assert result.reason == "rollback_finalize_compensation_failed"
    assert result.consistency_restored is False
    assert store.get_release("default", "RAG-R2").status is ReleaseStatus.PUBLISHED
    assert store.get_release("default", "RAG-R1").status is ReleaseStatus.SUPERSEDED
    assert qdrant.current_alias(CURRENT_ALIAS) == "rag_chunks_RAG-R1"
    assert store.current["default"] == "RAG-R1"


def test_rollback_reports_five_minute_rto_protocol():
    service, qdrant, store, cache = _validated()
    assert service.publish("default", "RAG-R2").succeeded is True
    timed = ReleasePublisher(
        qdrant, store, cache, _profile(), clock=StepClock(0.0, 301.0)
    )

    result = timed.rollback("default", "RAG-R2")

    assert result.succeeded is True
    assert result.elapsed_ms == 301_000
    assert result.rto_met is False


@pytest.mark.parametrize("target", ["published", "previous"])
def test_rollback_tampered_record_fails_before_alias_or_store_write(target):
    service, qdrant, store, _ = _validated()
    assert service.publish("default", "RAG-R2").succeeded is True
    if target == "published":
        record = store.records[("default", "RAG-R2")]
        store.records[("default", "RAG-R2")] = replace(record, manifest_sha256="")
        expected = "rollback_target_fact_invalid"
    else:
        record = store.records[("default", "RAG-R1")]
        store.records[("default", "RAG-R1")] = replace(
            record, embedding_profile=_profile("drifted")
        )
        expected = "rollback_previous_fact_invalid"
    before = (
        qdrant.switch_count, store.set_current_count, store.finalize_rollback_count,
        len(store.facts), qdrant.current_alias(CURRENT_ALIAS), store.current["default"],
    )

    result = service.rollback("default", "RAG-R2")

    after = (
        qdrant.switch_count, store.set_current_count, store.finalize_rollback_count,
        len(store.facts), qdrant.current_alias(CURRENT_ALIAS), store.current["default"],
    )
    assert result.reason == expected
    assert after == before

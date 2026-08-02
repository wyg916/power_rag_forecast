import hashlib
import json
from dataclasses import replace

import pytest

from knowledge_pipeline.enterprise.candidate_orchestrator import (
    CandidateCorpusArtifact,
    DocumentMetadata,
    EmbeddingProfile,
    ParsedSourceInput,
    build_candidate_corpus,
)
from knowledge_pipeline.enterprise.chunking import build_candidate
from knowledge_pipeline.enterprise.contracts import AdmissionStatus, SourceLedgerEntry
from knowledge_pipeline.enterprise.frozen_export import export_frozen_records
from knowledge_pipeline.enterprise.ledger import serialize_ledger
from knowledge_pipeline.enterprise.parsed_contracts import ParsedBlock, ParsedDocument, ParseStatus
from knowledge_pipeline.enterprise.release_handoff import (
    ApprovedEmbeddingArtifact,
    CandidateReleaseHandoffError,
    CandidateReleaseReceipt,
    build_candidate_release_envelope,
    handoff_candidate_release,
)


CREATED_AT = "2026-07-31T00:00:00Z"
PROFILE = EmbeddingProfile("sentence_transformers", "BAAI/bge-large-zh-v1.5", 1024, "e" * 64, "bm25-zh-v1")
APPROVED = ApprovedEmbeddingArtifact(
    "sentence_transformers", "BAAI/bge-large-zh-v1.5", "bge-large-zh-r1", 1024, "e" * 64, "bm25-zh-v1",
)


def _hash(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _ledger() -> list[SourceLedgerEntry]:
    source_hash = hashlib.sha256(b"ready-source").hexdigest()
    entries = [
        SourceLedgerEntry("src_000", "fixtures/000.docx", "000.docx", 10, source_hash, "docx", "docx", AdmissionStatus.READY),
        SourceLedgerEntry(
            "src_001", "fixtures/001.docx", "001.docx", 10, source_hash, "docx", "docx",
            AdmissionStatus.DUPLICATE, "duplicate_content", "src_000", "fixtures/000.docx",
        ),
        SourceLedgerEntry(
            "src_002", "fixtures/002.wps", "002.wps", 10, hashlib.sha256(b"quarantined").hexdigest(),
            "wps", "wps", AdmissionStatus.QUARANTINED, "conversion_required",
        ),
    ]
    for index in range(3, 83):
        entries.append(
            SourceLedgerEntry(
                f"src_{index:03d}", f"fixtures/{index:03d}.bin", f"{index:03d}.bin", 10,
                hashlib.sha256(f"corrupt-{index}".encode()).hexdigest(), "bin", "unknown",
                AdmissionStatus.CORRUPT, "unsupported_format",
            )
        )
    return entries


def _artifact(ledger: list[SourceLedgerEntry]) -> CandidateCorpusArtifact:
    ready = ledger[0]
    document = ParsedDocument(
        ready.source_id, "fixture.docx", "docx", ready.sha256, "fixture", "1", ParseStatus.READY,
        (ParsedBlock("block_0", 1, "paragraph", "candidate release evidence", ("release",)),),
    )
    return build_candidate_corpus(
        ledger_entries=ledger,
        parsed_sources={ready.source_id: ParsedSourceInput(ready.source_id, ready.sha256, document)},
        document_metadata={ready.source_id: DocumentMetadata(ready.source_id, "Release Guide", "power", CREATED_AT)},
        candidate_release_id="RAG-R1",
        tenant_id="default",
        created_at=CREATED_AT,
        embedding_profile=PROFILE,
        candidate_builder=lambda value: build_candidate(value, token_counter=len, max_tokens=128),
        frozen_exporter=export_frozen_records,
    )


def _build(artifact: CandidateCorpusArtifact, ledger: list[SourceLedgerEntry], **overrides):
    kwargs = {
        "serialized_ledger": serialize_ledger(ledger),
        "expected_tenant_id": "default",
        "expected_release_id": "RAG-R1",
        "approved_embedding": APPROVED,
    }
    kwargs.update(overrides)
    return build_candidate_release_envelope(artifact, **kwargs)


def _rehash(value: dict, *, manifest: bool = False) -> CandidateCorpusArtifact:
    if manifest:
        base = dict(value["candidate_manifest"])
        base.pop("corpus_sha256", None)
        value["candidate_manifest"]["corpus_sha256"] = _hash(base)
    outer = dict(value)
    outer.pop("artifact_sha256", None)
    value["artifact_sha256"] = _hash(outer)
    return CandidateCorpusArtifact(value)


class MemorySink:
    def __init__(self) -> None:
        self.payloads: list[bytes] = []

    def store(self, envelope) -> CandidateReleaseReceipt:
        self.payloads.append(envelope.to_json_bytes())
        return CandidateReleaseReceipt("default", "RAG-R1", envelope.value["envelope_sha256"], True)


def test_release_envelope_is_deterministic_complete_and_memory_sink_receives_exact_bytes() -> None:
    ledger = _ledger()
    artifact = _artifact(ledger)
    first = _build(artifact, ledger)
    second = _build(artifact, ledger)
    sink = MemorySink()
    handed = handoff_candidate_release(
        artifact,
        serialized_ledger=serialize_ledger(ledger),
        expected_tenant_id="default",
        expected_release_id="RAG-R1",
        approved_embedding=APPROVED,
        sink=sink,
    )

    assert first.to_json_bytes() == second.to_json_bytes() == handed.to_json_bytes() == sink.payloads[0]
    assert first.value["schemas"] == {
        "source_ledger": "rag-source-ledger/v1",
        "orchestration": "rag-candidate-orchestration/v1",
        "frozen_corpus": "rag-candidate-corpus/v1",
    }
    assert first.value["counts"] == {
        "ledger": 83, "documents": 1, "versions": 1, "chunks": 1, "assets": 0,
        "duplicates": 1, "isolations": 81,
    }
    assert first.value["embedding"] == {
        "provider": "sentence_transformers", "model": "BAAI/bge-large-zh-v1.5",
        "approved_version": "bge-large-zh-r1", "dimension": 1024, "model_sha256": "e" * 64,
        "sparse_profile": "bm25-zh-v1",
    }
    assert set(first.value["hashes"]) == {
        "ledger_sha256", "corpus_sha256", "manifest_sha256", "artifact_sha256",
    }


def test_hash_and_ledger_tampering_fail_closed() -> None:
    ledger = _ledger()
    artifact = _artifact(ledger)
    artifact.value["candidate_manifest"]["documents"][0]["title"] = "tampered"
    with pytest.raises(CandidateReleaseHandoffError, match="^candidate_artifact_hash_mismatch$"):
        _build(artifact, ledger)

    clean = _artifact(ledger)
    tampered_ledger = serialize_ledger(ledger).replace(b"unsupported_format", b"unsupported_value", 1)
    with pytest.raises(CandidateReleaseHandoffError, match="^source_ledger_hash_mismatch$"):
        _build(clean, ledger, serialized_ledger=tampered_ledger)


@pytest.mark.parametrize("mode", ("schema", "counts"))
def test_rehashed_schema_or_count_tampering_still_fails_closed(mode: str) -> None:
    ledger = _ledger()
    value = json.loads(_artifact(ledger).to_json_bytes())
    if mode == "schema":
        value["candidate_manifest"].pop("release_status")
        artifact = _rehash(value, manifest=True)
        code = "candidate_manifest_schema_invalid"
    else:
        value["counts"]["documents"] += 1
        artifact = _rehash(value)
        code = "candidate_counts_mismatch"
    with pytest.raises(CandidateReleaseHandoffError, match=f"^{code}$"):
        _build(artifact, ledger)


def test_cross_tenant_and_embedding_profile_mismatch_fail_closed() -> None:
    ledger = _ledger()
    value = json.loads(_artifact(ledger).to_json_bytes())
    value["tenant_id"] = value["candidate_manifest"]["tenant_id"] = "tenant-other"
    artifact = _rehash(value, manifest=True)
    with pytest.raises(CandidateReleaseHandoffError, match="^candidate_identity_mismatch$"):
        _build(artifact, ledger)

    with pytest.raises(CandidateReleaseHandoffError, match="^embedding_profile_mismatch$"):
        _build(_artifact(ledger), ledger, approved_embedding=replace(APPROVED, model_sha256="f" * 64))


def test_unknown_sink_failure_is_redacted_and_aborts_handoff() -> None:
    class BrokenSink:
        def store(self, envelope) -> None:
            raise RuntimeError(r"E:\private\release.json:raw-sensitive-content")

    ledger = _ledger()
    with pytest.raises(CandidateReleaseHandoffError) as captured:
        handoff_candidate_release(
            _artifact(ledger),
            serialized_ledger=serialize_ledger(ledger),
            expected_tenant_id="default",
            expected_release_id="RAG-R1",
            approved_embedding=APPROVED,
            sink=BrokenSink(),
        )
    assert str(captured.value) == "candidate_sink_internal_error"
    assert "private" not in str(captured.value)
    assert "raw-sensitive-content" not in str(captured.value)


@pytest.mark.parametrize("mode", ("none", "tenant", "release", "hash", "stored"))
def test_sink_receipt_must_prove_exact_persisted_envelope(mode: str) -> None:
    class InvalidReceiptSink:
        def store(self, envelope):
            if mode == "none":
                return None
            return CandidateReleaseReceipt(
                "tenant-other" if mode == "tenant" else "default",
                "RAG-other" if mode == "release" else "RAG-R1",
                "0" * 64 if mode == "hash" else envelope.value["envelope_sha256"],
                mode != "stored",
            )

    ledger = _ledger()
    with pytest.raises(CandidateReleaseHandoffError, match="^candidate_sink_receipt_invalid$"):
        handoff_candidate_release(
            _artifact(ledger),
            serialized_ledger=serialize_ledger(ledger),
            expected_tenant_id="default",
            expected_release_id="RAG-R1",
            approved_embedding=APPROVED,
            sink=InvalidReceiptSink(),
        )

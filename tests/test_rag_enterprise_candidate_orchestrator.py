import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from knowledge_pipeline.enterprise.candidate_orchestrator import (
    CandidateOrchestrationError,
    DocumentMetadata,
    EmbeddingProfile,
    ParsedSourceInput,
    build_candidate_corpus,
)
from knowledge_pipeline.enterprise.chunking import ChunkBuildError, build_candidate, derive_version_id
from knowledge_pipeline.enterprise.contracts import AdmissionStatus, SourceLedgerEntry
from knowledge_pipeline.enterprise.frozen_export import FrozenExportError, export_frozen_records
from knowledge_pipeline.enterprise.multimodal_mapping import ocr_to_parsed_document
from knowledge_pipeline.enterprise.ocr_contracts import (
    OCRApprovalPolicy, OCRProviderProfile, OCRRequest, OCRResult, VisionElement, element_hash,
)
from knowledge_pipeline.enterprise.parsed_contracts import BoundingBox, ParsedAsset, ParsedBlock, ParsedDocument, ParseStatus


PROFILE = EmbeddingProfile("sentence_transformers", "BAAI/bge-large-zh-v1.5", 1024, "e" * 64, "bm25-zh-v1")
CREATED_AT = "2026-07-31T00:00:00Z"


def _sha(index: int) -> str:
    return hashlib.sha256(f"fixture-source-{index}".encode()).hexdigest()


def _entry(index: int, status: AdmissionStatus, *, source_hash: str | None = None) -> SourceLedgerEntry:
    source_id = f"src_{index:03d}"
    relative_path = f"fixtures/{index:03d}.docx"
    reason = ""
    duplicate_id = duplicate_path = ""
    if status is AdmissionStatus.DUPLICATE:
        reason = "duplicate_content"
        duplicate_id = "src_000"
        duplicate_path = "fixtures/000.docx"
    elif status is AdmissionStatus.QUARANTINED:
        reason = "fixture_quarantined"
    elif status is AdmissionStatus.CORRUPT:
        reason = "fixture_corrupt"
    return SourceLedgerEntry(
        source_id=source_id,
        relative_path=relative_path,
        file_name=f"{index:03d}.docx",
        size_bytes=100 + index,
        sha256=source_hash or _sha(index),
        declared_format="docx",
        detected_format="docx",
        admission_status=status,
        isolation_reason=reason,
        duplicate_of_source_id=duplicate_id,
        duplicate_of_path=duplicate_path,
    )


def _ledger(two_ready: bool = True) -> list[SourceLedgerEntry]:
    entries = [_entry(0, AdmissionStatus.READY)]
    if two_ready:
        entries.append(_entry(1, AdmissionStatus.READY))
        entries.append(_entry(2, AdmissionStatus.DUPLICATE, source_hash=_sha(0)))
        entries.append(_entry(3, AdmissionStatus.QUARANTINED))
        start = 4
    else:
        start = 1
    entries.extend(_entry(index, AdmissionStatus.CORRUPT) for index in range(start, 83))
    return entries


def _metadata(source_id: str) -> DocumentMetadata:
    return DocumentMetadata(source_id, f"标题-{source_id}", "power-market", CREATED_AT)


def _parsed_sources(ledger: list[SourceLedgerEntry]):
    by_id = {entry.source_id: entry for entry in ledger}
    direct = ParsedDocument(
        "src_000", "fixture-0.docx", "docx", by_id["src_000"].sha256, "fixture-docx", "1", ParseStatus.READY,
        (ParsedBlock("block_0", 1, "paragraph", "直接解析的规则正文", ("规则",)),),
    )
    transformed_hash = "f" * 64
    layout = ParsedDocument(
        "src_001", "fixture-1.pdf", "pdf", transformed_hash, "approved-ocr", "1", ParseStatus.READY,
        (ParsedBlock("block_1", 1, "image", "图表解释文本", ("第1页",), 1, BoundingBox(0, 0, 100, 80)),),
        assets=(ParsedAsset("image_1", 1, "image", "ready", 1, BoundingBox(0, 0, 100, 80), content_hash="a" * 64),),
        page_count=1,
    )
    return {
        "src_000": ParsedSourceInput("src_000", by_id["src_000"].sha256, direct),
        "src_001": ParsedSourceInput("src_001", by_id["src_001"].sha256, layout, transformed_hash),
    }


def _builder(document: ParsedDocument):
    return build_candidate(document, token_counter=len, max_tokens=128)


def _build(ledger, parsed, metadata, *, builder=_builder, exporter=export_frozen_records, profile=PROFILE, tenant="default"):
    return build_candidate_corpus(
        ledger_entries=ledger,
        parsed_sources=parsed,
        document_metadata=metadata,
        candidate_release_id="RAG-R1",
        tenant_id=tenant,
        created_at=CREATED_AT,
        embedding_profile=profile,
        candidate_builder=builder,
        frozen_exporter=exporter,
    )


def test_fixture_candidate_manifest_is_frozen_valid_deduplicated_and_byte_stable() -> None:
    ledger = _ledger()
    parsed = _parsed_sources(ledger)
    metadata = {source_id: _metadata(source_id) for source_id in parsed}
    first = _build(ledger, parsed, metadata)
    second = _build(list(reversed(ledger)), dict(reversed(list(parsed.items()))), metadata)

    assert first.to_json_bytes() == second.to_json_bytes()
    assert first.value["counts"] == {
        "ledger": 83, "documents": 2, "chunks": 2, "assets": 1, "duplicates": 1, "isolations": 80,
    }
    assert first.value["duplicates"] == [
        {"source_id": "src_002", "canonical_source_id": "src_000", "source_sha256": _sha(0)}
    ]
    assert {item["source_id"] for item in first.candidate_manifest["documents"]} == {"src_000", "src_001"}
    transformed = next(item for item in first.value["versions"] if item["source_id"] == "src_001")
    assert transformed["source_sha256"] == _sha(1)
    assert transformed["content_sha256"] == "f" * 64 and transformed["transformed"] is True
    assert first.candidate_manifest["ledger_summary"] == {
        "total": 83, "ready": 2, "quarantined": 1, "duplicate": 1, "corrupt": 79,
    }
    assert len(first.value["source_ledger"]["sha256"]) == 64

    root = Path(__file__).parents[1]
    schema = json.loads((root / "docs/codex/contracts/rag_candidate_corpus_v1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(first.candidate_manifest)
    outer = dict(first.value)
    artifact_hash = outer.pop("artifact_sha256")
    assert artifact_hash == hashlib.sha256(json.dumps(outer, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    frozen = dict(first.candidate_manifest)
    corpus_hash = frozen.pop("corpus_sha256")
    assert corpus_hash == hashlib.sha256(json.dumps(frozen, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_actual_i4_fixture_mapping_can_be_injected_into_candidate(tmp_path: Path) -> None:
    image_path = tmp_path / "scan.jpg"
    image_path.write_bytes(b"fixture-scan")
    source_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
    ledger = _ledger(two_ready=False)
    ledger[0] = replace(
        ledger[0], relative_path="fixtures/000.jpg", file_name="000.jpg", sha256=source_hash,
        size_bytes=image_path.stat().st_size, declared_format="jpg", detected_format="jpg",
    )
    base = ParsedDocument("src_000", str(image_path), "jpg", source_hash, "approved-ocr", "1", ParseStatus.READY)
    version_id = derive_version_id(base)
    profile = OCRProviderProfile("approved-ocr", "1")
    policy = OCRApprovalPolicy((profile,))
    request = OCRRequest(
        image_path, "jpg", source_hash, "default", version_id, profile,
        ((1, 100, 80),), ((1, ()),),
    )
    text = "设备图示"
    element = VisionElement(
        "image_ocr", source_hash, "default", version_id, 1, 100, 80,
        BoundingBox(0, 0, 100, 80), "image", "ready", text=text,
        confidence=0.99, content_hash=element_hash(text),
    )
    result = OCRResult(source_hash, "default", version_id, "completed", "approved-ocr", "1", (element,))
    parsed = ocr_to_parsed_document(request, result, policy, source_id="src_000")
    artifact = _build(
        ledger,
        {"src_000": ParsedSourceInput("src_000", source_hash, parsed)},
        {"src_000": _metadata("src_000")},
    )
    assert artifact.value["counts"]["documents"] == 1
    assert artifact.value["counts"]["assets"] == 1


@pytest.mark.parametrize(
    "mode", ("missing", "hash", "ocr", "conversion", "empty", "locator", "version", "frozen_locator"),
)
def test_ready_source_gate_failure_records_isolation_and_excludes_version(mode: str) -> None:
    ledger = _ledger(two_ready=False)
    entry = ledger[0]
    document = ParsedDocument(
        entry.source_id, "fixture.docx", "docx", entry.sha256, "fixture", "1", ParseStatus.READY,
        (ParsedBlock("block", 1, "paragraph", "可验证证据"),),
    )
    source = ParsedSourceInput(entry.source_id, entry.sha256, document)
    parsed = {entry.source_id: source}
    builder = _builder
    exporter = export_frozen_records
    if mode == "missing":
        parsed = {}
    elif mode == "hash":
        parsed = {entry.source_id: replace(source, source_sha256="0" * 64)}
    elif mode == "ocr":
        parsed = {entry.source_id: replace(source, document=replace(document, status=ParseStatus.OCR_REQUIRED))}
    elif mode == "conversion":
        parsed = {
            entry.source_id: replace(
                source, document=replace(document, status=ParseStatus.QUARANTINED, isolation_reason="conversion_incomplete"),
            )
        }
    elif mode in {"empty", "locator"}:
        def builder(value):
            build = _builder(value)
            if mode == "empty":
                return replace(build, chunks=())
            first = build.chunks[0]
            broken = replace(first, citation=replace(first.citation, char_end=999))
            return replace(build, chunks=(broken,))
    elif mode in {"version", "frozen_locator"}:
        def exporter(build):
            records = export_frozen_records(build)
            if mode == "version":
                return records | {"version_id": "version-wrong"}
            altered = json.loads(json.dumps(records))
            altered["chunks"][0]["citation"]["char_end"] += 1
            return altered

    artifact = _build(ledger, parsed, {entry.source_id: _metadata(entry.source_id)}, builder=builder, exporter=exporter)
    assert artifact.value["counts"]["documents"] == 0
    assert artifact.value["counts"]["chunks"] == 0
    isolated = next(item for item in artifact.value["isolations"] if item["source_id"] == entry.source_id)
    assert isolated["ledger_status"] == "ready" and isolated["reason"]


def test_global_profile_tenant_and_duplicate_canonical_gates_fail_closed() -> None:
    ledger = _ledger()
    parsed = _parsed_sources(ledger)
    metadata = {source_id: _metadata(source_id) for source_id in parsed}
    with pytest.raises(CandidateOrchestrationError, match="embedding_profile_not_approved"):
        _build(ledger, parsed, metadata, profile=replace(PROFILE, dimension=256))
    with pytest.raises(CandidateOrchestrationError, match="candidate_identity_invalid"):
        _build(ledger, parsed, metadata, tenant="other")
    duplicate_index = next(index for index, item in enumerate(ledger) if item.admission_status is AdmissionStatus.DUPLICATE)
    broken = list(ledger)
    broken[duplicate_index] = replace(broken[duplicate_index], duplicate_of_source_id="src_missing")
    with pytest.raises(CandidateOrchestrationError, match="ledger_duplicate_canonical_invalid"):
        _build(broken, parsed, metadata)

    duplicate = ledger[duplicate_index]
    duplicate_document = replace(parsed["src_000"].document, source_id=duplicate.source_id)
    duplicate_input = ParsedSourceInput(duplicate.source_id, duplicate.sha256, duplicate_document)
    with pytest.raises(CandidateOrchestrationError, match="parsed_source_not_canonical_ready"):
        _build(ledger, parsed | {duplicate.source_id: duplicate_input}, metadata)


@pytest.mark.parametrize(
    ("stage", "expected_code"),
    (("builder", "candidate_builder_internal_error"), ("exporter", "frozen_exporter_internal_error")),
)
def test_unknown_callback_error_aborts_candidate_with_redacted_code(stage: str, expected_code: str) -> None:
    ledger = _ledger(two_ready=False)
    parsed = {"src_000": _parsed_sources(ledger)["src_000"]}
    metadata = {"src_000": _metadata("src_000")}
    secret = r"E:\private\source.docx:raw-sensitive-content"

    def broken_builder(document):
        if stage == "builder":
            raise RuntimeError(secret)
        return _builder(document)

    def broken_exporter(build):
        if stage == "exporter":
            raise RuntimeError(secret)
        return export_frozen_records(build)

    with pytest.raises(CandidateOrchestrationError) as captured:
        _build(ledger, parsed, metadata, builder=broken_builder, exporter=broken_exporter)

    assert str(captured.value) == expected_code
    assert "private" not in str(captured.value)
    assert "raw-sensitive-content" not in str(captured.value)


@pytest.mark.parametrize("stage", ("builder", "exporter"))
def test_known_callback_data_error_isolates_only_affected_document(stage: str) -> None:
    ledger = _ledger(two_ready=False)
    parsed = {"src_000": _parsed_sources(ledger)["src_000"]}
    metadata = {"src_000": _metadata("src_000")}

    def rejected_builder(document):
        if stage == "builder":
            raise ChunkBuildError("empty_block:raw-sensitive-content")
        return _builder(document)

    def rejected_exporter(build):
        if stage == "exporter":
            raise FrozenExportError("chunk_build_quality_failed:raw-sensitive-content")
        return export_frozen_records(build)

    artifact = _build(ledger, parsed, metadata, builder=rejected_builder, exporter=rejected_exporter)

    assert artifact.value["counts"]["documents"] == 0
    isolation = next(item for item in artifact.value["isolations"] if item["source_id"] == "src_000")
    expected_reason = "empty_block" if stage == "builder" else "chunk_build_quality_failed"
    assert isolation["reason"] == expected_reason
    assert "raw-sensitive-content" not in artifact.to_json_bytes().decode("utf-8")


@pytest.mark.parametrize(
    ("stage", "expected_reason"), (("builder", "chunk_build_rejected"), ("exporter", "frozen_export_rejected")),
)
def test_unclassified_known_error_is_normalized_without_dynamic_text(stage: str, expected_reason: str) -> None:
    ledger = _ledger(two_ready=False)
    parsed = {"src_000": _parsed_sources(ledger)["src_000"]}
    secret = r"unclassified E:\private\source.docx raw-sensitive-content"

    def rejected_builder(document):
        if stage == "builder":
            raise ChunkBuildError(secret)
        return _builder(document)

    def rejected_exporter(build):
        if stage == "exporter":
            raise FrozenExportError(secret)
        return export_frozen_records(build)

    artifact = _build(
        ledger, parsed, {"src_000": _metadata("src_000")}, builder=rejected_builder, exporter=rejected_exporter,
    )
    isolation = next(item for item in artifact.value["isolations"] if item["source_id"] == "src_000")
    assert isolation["reason"] == expected_reason
    assert "private" not in artifact.to_json_bytes().decode("utf-8")

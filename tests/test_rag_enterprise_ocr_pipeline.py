import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from backend.app.knowledge_enterprise_contracts import AssetContract, CitationContract
from knowledge_pipeline.enterprise.chunking import build_candidate, derive_version_id
from knowledge_pipeline.enterprise.frozen_export import export_frozen_records
from knowledge_pipeline.enterprise.multimodal_mapping import ocr_asset_records, ocr_to_parsed_document
from knowledge_pipeline.enterprise.ocr_contracts import (
    OCRApprovalPolicy, OCRProviderProfile, OCRRequest, OCRResult, VisionElement, element_hash,
)
from knowledge_pipeline.enterprise.ocr_pipeline import OCRValidationError, run_ocr, validate_ocr_result
from knowledge_pipeline.enterprise.parsed_contracts import BoundingBox, ParsedDocument, ParseStatus


class FakeProvider:
    def __init__(self, result: OCRResult) -> None:
        self.result = result

    def analyze(self, request: OCRRequest) -> OCRResult:
        return self.result


def _source(tmp_path: Path, suffix: str) -> tuple[Path, str]:
    path = tmp_path / f"scan.{suffix}"
    path.write_bytes(b"scan-source-" + suffix.encode())
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _version(path: Path, source_hash: str, source_id: str, source_format: str, provider_version: str = "1") -> str:
    document = ParsedDocument(source_id, str(path), source_format, source_hash, "fake", provider_version, ParseStatus.READY)
    return derive_version_id(document)


def _element(source_hash: str, version_id: str, element_id: str, kind: str, text: str = "", cells=(), *, page=1, y=0) -> VisionElement:
    cells = tuple(tuple(cell for cell in row) for row in cells)
    return VisionElement(
        element_id, source_hash, "default", version_id, page, 1000, 800,
        BoundingBox(10, y + 10, 900, y + 100), kind, "ready", text, cells, 0.99, element_hash(text, cells),
    )


def test_jpg_multi_element_result_maps_to_candidate_and_assets(tmp_path: Path) -> None:
    path, source_hash = _source(tmp_path, "jpg")
    version_id = _version(path, source_hash, "src_jpg", "jpg")
    profile = OCRProviderProfile("fake-paddleocr-vl", "1")
    policy = OCRApprovalPolicy((profile,))
    request = OCRRequest(path, "jpg", source_hash, "default", version_id, profile, ((1, 1000, 800),), ((1, ("100", "20")),))
    elements = (
        _element(source_hash, version_id, "text_1", "text", "电价100元", y=0),
        _element(source_hash, version_id, "table_1", "table", cells=(("时段", "价格"), ("峰", "20")), y=120),
        _element(source_hash, version_id, "formula_1", "formula", "P=U×I", y=240),
        _element(source_hash, version_id, "chart_1", "chart", "价格趋势图", y=360),
        _element(source_hash, version_id, "image_1", "image", "设备现场图", y=480),
    )
    result = OCRResult(source_hash, "default", version_id, "completed", "fake-paddleocr-vl", "1", elements)
    validated = run_ocr(request, FakeProvider(result), policy)
    parsed = ocr_to_parsed_document(request, validated, policy, source_id="src_jpg")
    candidate = build_candidate(parsed, token_counter=len, max_tokens=120)
    frozen = export_frozen_records(candidate)
    asset_records = ocr_asset_records(request, validated, policy)
    assert len(parsed.blocks) == 5 and len(parsed.tables) == 1 and len(parsed.assets) == 3
    assert {asset["asset_type"] for asset in frozen["assets"]} == {"table", "formula", "chart", "image"}
    assert {record["version_id"] for record in asset_records} == {candidate.version_id}
    assert {record["content_hash"] for record in asset_records} == {asset["content_hash"] for asset in frozen["assets"]}
    assert all(chunk.citation.page == 1 and chunk.citation.bbox for chunk in candidate.chunks)
    assert all(AssetContract.model_validate(record).tenant_id == "default" for record in asset_records)
    first_chunk = frozen["chunks"][0]
    citation = first_chunk["citation"] | {
        "document_id": candidate.document_id,
        "chunk_id": first_chunk["chunk_id"],
        "release_id": "RAG-R1",
    }
    assert CitationContract.model_validate(citation).version_id == candidate.version_id


def test_scanned_pdf_keeps_page_size_bbox_and_page_identity(tmp_path: Path) -> None:
    path, source_hash = _source(tmp_path, "pdf")
    version_id = _version(path, source_hash, "src_pdf", "pdf")
    profile = OCRProviderProfile("fake", "1")
    policy = OCRApprovalPolicy((profile,))
    request = OCRRequest(
        path, "pdf", source_hash, "default", version_id, profile,
        ((1, 1000, 800), (2, 1000, 800)), ((1, ("10",)), (2, ("20",))),
    )
    elements = (
        _element(source_hash, version_id, "p1", "text", "第一页10", page=1),
        _element(source_hash, version_id, "p2", "text", "第二页20", page=2),
    )
    result = run_ocr(
        request, FakeProvider(OCRResult(source_hash, "default", version_id, "completed", "fake", "1", elements)), policy,
    )
    parsed = ocr_to_parsed_document(request, result, policy, source_id="src_pdf")
    assert parsed.page_count == 2
    assert [block.page for block in parsed.blocks] == [1, 2]
    assert all(block.bbox is not None for block in parsed.blocks)


def test_ocr_bad_results_fail_closed_before_mapping_or_chunking(tmp_path: Path) -> None:
    path, source_hash = _source(tmp_path, "jpg")
    version_id = _version(path, source_hash, "blocked", "jpg")
    profile = OCRProviderProfile("fake", "1")
    policy = OCRApprovalPolicy((profile,))
    request = OCRRequest(path, "jpg", source_hash, "default", version_id, profile, ((1, 1000, 800),), ((1, ("100",)),))
    valid = _element(source_hash, version_id, "e1", "text", "原值100")
    bad_results = (
        OCRResult(source_hash, "default", version_id, "failed", "fake", "1", (valid,)),
        OCRResult("f" * 64, "default", version_id, "completed", "fake", "1", (valid,)),
        OCRResult(source_hash, "default", version_id, "completed", "fake", "1", ()),
        OCRResult(source_hash, "default", version_id, "completed", "fake", "1", (valid, valid)),
        OCRResult(source_hash, "default", version_id, "completed", "fake", "1", (replace(valid, page=2),)),
        OCRResult(source_hash, "default", version_id, "completed", "fake", "1", (replace(valid, bbox=BoundingBox(0, 0, 2000, 1)),)),
        OCRResult(source_hash, "default", version_id, "completed", "fake", "1", (replace(valid, content_hash="bad"),)),
        OCRResult(source_hash, "default", version_id, "completed", "fake", "1", (replace(valid, text="设备A999", content_hash=element_hash("设备A999")),)),
        OCRResult(source_hash, "other", version_id, "completed", "fake", "1", (valid,)),
        OCRResult(source_hash, "default", version_id, "completed", "fake", "1", (replace(valid, status="ocr_required"),)),
        OCRResult(source_hash, "default", version_id, "completed", "fake", "1", (replace(valid, version_id="version-other"),)),
        OCRResult(
            source_hash, "default", version_id, "completed", "fake", "1",
            (replace(valid, asset_type="table", text="", cells=(("",),), content_hash=element_hash("", (("",),))),),
        ),
        OCRResult(source_hash, "default", version_id, "completed", "unknown-provider", "1", (valid,)),
        OCRResult(source_hash, "default", version_id, "completed", "fake", "2", (valid,)),
    )
    expected = {
        "ocr_not_completed", "ocr_source_hash_mismatch", "ocr_result_empty",
        "ocr_element_id_missing_or_duplicate", "ocr_page_or_size_mismatch",
        "ocr_bbox_out_of_bounds", "ocr_element_hash_mismatch", "ocr_numeric_hallucination",
        "ocr_result_identity_mismatch", "ocr_element_not_ready", "ocr_element_identity_mismatch",
        "ocr_element_content_invalid",
        "ocr_provider_profile_mismatch",
    }
    observed = set()
    for bad in bad_results:
        observed.update(issue.code for issue in validate_ocr_result(request, bad, policy))
        with pytest.raises(OCRValidationError, match="ocr_validation_failed"):
            run_ocr(request, FakeProvider(bad), policy)
        with pytest.raises(OCRValidationError, match="ocr_mapping_rejected"):
            ocr_to_parsed_document(request, bad, policy, source_id="blocked")
    assert expected <= observed

    bad_request = replace(request, source_sha256="0" * 64)
    with pytest.raises(OCRValidationError, match="ocr_request_source_hash_mismatch"):
        validate_ocr_result(
            bad_request, OCRResult(source_hash, "default", version_id, "completed", "fake", "1", (valid,)), policy,
        )
    with pytest.raises(OCRValidationError, match="ocr_request_digit_evidence_incomplete"):
        validate_ocr_result(
            replace(request, source_page_digits=()),
            OCRResult(source_hash, "default", version_id, "completed", "fake", "1", (valid,)),
            policy,
        )
    with pytest.raises(OCRValidationError, match="ocr_request_identity_invalid"):
        validate_ocr_result(
            replace(request, tenant_id="other"),
            OCRResult(source_hash, "other", version_id, "completed", "fake", "1", (valid,)),
            policy,
        )
    with pytest.raises(OCRValidationError, match="ocr_expected_profile_invalid"):
        validate_ocr_result(
            replace(request, expected_profile=OCRProviderProfile("", "")),
            OCRResult(source_hash, "default", version_id, "completed", "fake", "1", (valid,)),
            policy,
        )
    wrong_version = "version-wrong"
    wrong_request = replace(request, version_id=wrong_version)
    wrong_element = replace(valid, version_id=wrong_version)
    wrong_result = OCRResult(source_hash, "default", wrong_version, "completed", "fake", "1", (wrong_element,))
    assert validate_ocr_result(wrong_request, wrong_result, policy) == ()
    with pytest.raises(OCRValidationError, match="ocr_mapping_version_mismatch"):
        ocr_to_parsed_document(wrong_request, wrong_result, policy, source_id="blocked")

    unknown = OCRProviderProfile("unknown-provider", "9")
    unknown_request = replace(request, expected_profile=unknown)
    unknown_result = OCRResult(source_hash, "default", version_id, "completed", "unknown-provider", "9", (valid,))
    with pytest.raises(OCRValidationError, match="ocr_expected_profile_not_approved"):
        validate_ocr_result(unknown_request, unknown_result, policy)

from __future__ import annotations

import re
from dataclasses import dataclass
from math import isfinite
from numbers import Real

from .ocr_contracts import (
    ELEMENT_KINDS,
    OCR_SOURCE_FORMATS,
    OCRApprovalPolicy,
    OCRProvider,
    OCRRequest,
    OCRResult,
    element_hash,
    element_payload,
)
from .controlled_conversion import sha256_file


NUMBER_PATTERN = re.compile(r"(?<!\d)[+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)%?(?!\d)")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class OCRValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class OCRIssue:
    code: str
    element_id: str = ""


def _numbers(value: str) -> set[str]:
    return {match.group(0).replace(",", "") for match in NUMBER_PATTERN.finditer(value)}


def _finite_real(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, Real) and isfinite(float(value))


def _request_maps(request: OCRRequest) -> tuple[dict[int, tuple[float, float]], dict[int, set[str]]]:
    sizes: dict[int, tuple[float, float]] = {}
    for page, width, height in request.page_sizes:
        if (
            isinstance(page, bool)
            or not isinstance(page, int)
            or page in sizes
            or page < 1
            or not _finite_real(width)
            or not _finite_real(height)
            or width <= 0
            or height <= 0
        ):
            raise OCRValidationError("ocr_request_page_size_invalid")
        sizes[page] = (width, height)
    digits: dict[int, set[str]] = {}
    for page, values in request.source_page_digits:
        if page in digits or page not in sizes:
            raise OCRValidationError("ocr_request_digit_evidence_invalid")
        normalized: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                raise OCRValidationError("ocr_request_digit_evidence_invalid")
            extracted = _numbers(value)
            if len(extracted) != 1:
                raise OCRValidationError("ocr_request_digit_evidence_invalid")
            normalized.update(extracted)
        digits[page] = normalized
    if not sizes:
        raise OCRValidationError("ocr_request_pages_empty")
    if set(digits) != set(sizes):
        raise OCRValidationError("ocr_request_digit_evidence_incomplete")
    return sizes, digits


def validate_ocr_result(
    request: OCRRequest,
    result: OCRResult,
    approval_policy: OCRApprovalPolicy,
) -> tuple[OCRIssue, ...]:
    source_format = request.source_format.lower().lstrip(".")
    if source_format not in OCR_SOURCE_FORMATS:
        raise OCRValidationError("ocr_source_format_forbidden")
    try:
        source = request.source_path.resolve(strict=True)
    except OSError as exc:
        raise OCRValidationError("ocr_source_unavailable") from exc
    if not source.is_file() or source.suffix.lower() not in ({".jpg", ".jpeg"} if source_format in {"jpg", "jpeg"} else {".pdf"}):
        raise OCRValidationError("ocr_source_format_mismatch")
    if sha256_file(source) != request.source_sha256:
        raise OCRValidationError("ocr_request_source_hash_mismatch")
    if request.tenant_id != "default" or not IDENTIFIER_PATTERN.fullmatch(request.version_id):
        raise OCRValidationError("ocr_request_identity_invalid")
    expected_profile = request.expected_profile
    if (
        not expected_profile.provider
        or not expected_profile.provider_version
        or len(expected_profile.provider) > 128
        or len(expected_profile.provider_version) > 128
        or any(mark in expected_profile.provider + expected_profile.provider_version for mark in ("\0", "\n", "\r"))
    ):
        raise OCRValidationError("ocr_expected_profile_invalid")
    if not approval_policy.allows(expected_profile):
        raise OCRValidationError("ocr_expected_profile_not_approved")
    sizes, source_digits = _request_maps(request)
    issues: list[OCRIssue] = []
    if result.status != "completed":
        issues.append(OCRIssue("ocr_not_completed"))
    if result.source_sha256 != request.source_sha256:
        issues.append(OCRIssue("ocr_source_hash_mismatch"))
    if (result.tenant_id, result.version_id) != (request.tenant_id, request.version_id):
        issues.append(OCRIssue("ocr_result_identity_mismatch"))
    if (result.provider, result.provider_version) != (expected_profile.provider, expected_profile.provider_version):
        issues.append(OCRIssue("ocr_provider_profile_mismatch"))
    if not result.elements:
        issues.append(OCRIssue("ocr_result_empty"))
    ids = [element.element_id for element in result.elements]
    if any(not element_id for element_id in ids) or len(set(ids)) != len(ids):
        issues.append(OCRIssue("ocr_element_id_missing_or_duplicate"))

    for element in result.elements:
        issue_id = element.element_id
        expected_size = sizes.get(element.page)
        if element.source_sha256 != request.source_sha256:
            issues.append(OCRIssue("ocr_element_source_hash_mismatch", issue_id))
        if (element.tenant_id, element.version_id) != (request.tenant_id, request.version_id):
            issues.append(OCRIssue("ocr_element_identity_mismatch", issue_id))
        size_valid = _finite_real(element.page_width) and _finite_real(element.page_height)
        if expected_size is None or not size_valid or expected_size != (element.page_width, element.page_height):
            issues.append(OCRIssue("ocr_page_or_size_mismatch", issue_id))
        box = element.bbox
        coordinates = (box.x0, box.y0, box.x1, box.y1)
        bbox_values_valid = all(_finite_real(value) for value in coordinates)
        if (
            expected_size is None
            or not size_valid
            or not bbox_values_valid
            or box.x0 < 0
            or box.y0 < 0
            or box.x1 <= box.x0
            or box.y1 <= box.y0
            or box.x1 > element.page_width
            or box.y1 > element.page_height
        ):
            issues.append(OCRIssue("ocr_bbox_out_of_bounds", issue_id))
        if element.asset_type not in ELEMENT_KINDS:
            issues.append(OCRIssue("ocr_element_kind_invalid", issue_id))
        try:
            payload = element_payload(element.text, element.cells)
        except (AttributeError, TypeError):
            payload = ""
        table_has_content = bool(element.cells) and any(
            any(isinstance(cell, str) and cell.strip() for cell in row) for row in element.cells
        )
        if (
            not payload
            or (element.asset_type == "table" and not table_has_content)
            or (element.asset_type != "table" and element.cells)
        ):
            issues.append(OCRIssue("ocr_element_content_invalid", issue_id))
        if element.status != "ready":
            issues.append(OCRIssue("ocr_element_not_ready", issue_id))
        try:
            expected_hash = element_hash(element.text, element.cells)
        except (AttributeError, TypeError):
            expected_hash = ""
        if element.content_hash != expected_hash:
            issues.append(OCRIssue("ocr_element_hash_mismatch", issue_id))
        if (
            isinstance(element.confidence, bool)
            or not isinstance(element.confidence, Real)
            or not isfinite(float(element.confidence))
            or not 0 <= element.confidence <= 1
        ):
            issues.append(OCRIssue("ocr_confidence_invalid", issue_id))
        added_numbers = _numbers(payload) - source_digits.get(element.page, set())
        if added_numbers:
            issues.append(OCRIssue("ocr_numeric_hallucination", issue_id))
    return tuple(issues)


def run_ocr(request: OCRRequest, provider: OCRProvider, approval_policy: OCRApprovalPolicy) -> OCRResult:
    try:
        result = provider.analyze(request)
    except Exception as exc:
        raise OCRValidationError("ocr_provider_failed") from exc
    issues = validate_ocr_result(request, result, approval_policy)
    if issues:
        raise OCRValidationError("ocr_validation_failed:" + ",".join(issue.code for issue in issues))
    return result

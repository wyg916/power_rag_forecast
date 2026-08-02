from __future__ import annotations

from .chunking import derive_version_id
from .ocr_contracts import OCRApprovalPolicy, OCRRequest, OCRResult
from .ocr_pipeline import OCRValidationError, validate_ocr_result
from .parsed_contracts import ParsedAsset, ParsedBlock, ParsedDocument, ParsedTable, ParseStatus


def _block_id(element_id: str) -> str:
    return f"block_{element_id}"


def ocr_to_parsed_document(
    request: OCRRequest,
    result: OCRResult,
    approval_policy: OCRApprovalPolicy,
    *,
    source_id: str,
) -> ParsedDocument:
    issues = validate_ocr_result(request, result, approval_policy)
    if issues:
        raise OCRValidationError("ocr_mapping_rejected:" + ",".join(issue.code for issue in issues))
    if not source_id:
        raise OCRValidationError("ocr_mapping_source_id_missing")

    ordered = sorted(
        result.elements,
        key=lambda item: (item.page, item.bbox.y0, item.bbox.x0, item.asset_type, item.element_id),
    )
    blocks: list[ParsedBlock] = []
    tables: list[ParsedTable] = []
    assets: list[ParsedAsset] = []
    for order, element in enumerate(ordered, start=1):
        section = (f"第{element.page}页",)
        if element.asset_type == "table":
            tables.append(ParsedTable(element.element_id, order, element.cells, page=element.page, bbox=element.bbox))
            blocks.append(
                ParsedBlock(_block_id(element.element_id), order, "table", "", section, element.page, element.bbox, element.element_id)
            )
            continue
        blocks.append(
            ParsedBlock(_block_id(element.element_id), order, element.asset_type, element.text.strip(), section, element.page, element.bbox)
        )
        if element.asset_type in {"formula", "chart", "image"}:
            assets.append(
                ParsedAsset(
                    element.element_id,
                    order,
                    element.asset_type,
                    "ready",
                    element.page,
                    element.bbox,
                    alt_text=element.text.strip(),
                    content_hash=element.content_hash,
                )
            )
    document = ParsedDocument(
        source_id=source_id,
        source_path=str(request.source_path),
        detected_format=request.source_format.lower().lstrip("."),
        content_hash=request.source_sha256,
        parser_name=result.provider,
        parser_version=result.provider_version,
        status=ParseStatus.READY,
        blocks=tuple(blocks),
        tables=tuple(tables),
        assets=tuple(assets),
        page_count=max(page for page, _, _ in request.page_sizes),
    )
    if derive_version_id(document) != request.version_id:
        raise OCRValidationError("ocr_mapping_version_mismatch")
    return document


def ocr_asset_records(
    request: OCRRequest,
    result: OCRResult,
    approval_policy: OCRApprovalPolicy,
) -> tuple[dict, ...]:
    issues = validate_ocr_result(request, result, approval_policy)
    if issues:
        raise OCRValidationError("ocr_asset_export_rejected:" + ",".join(issue.code for issue in issues))
    return tuple(
        {
            "asset_id": element.element_id,
            "tenant_id": element.tenant_id,
            "version_id": element.version_id,
            "asset_type": element.asset_type,
            "status": element.status,
            "content_hash": element.content_hash,
            "page": element.page,
            "bbox": (element.bbox.x0, element.bbox.y0, element.bbox.x1, element.bbox.y1),
        }
        for element in result.elements
        if element.asset_type in {"table", "formula", "chart", "image"}
    )

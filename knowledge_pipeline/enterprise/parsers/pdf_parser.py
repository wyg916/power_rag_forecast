from __future__ import annotations

from ..parsed_contracts import BoundingBox, ParsedAsset, ParsedBlock, ParseStatus
from .base import ParseContext, ParseFailure, element_id, finish


def _bbox(values) -> BoundingBox:
    return BoundingBox(*(round(float(value), 3) for value in values[:4]))


def parse_pdf(context: ParseContext):
    try:
        import fitz
    except ImportError as exc:
        raise ParseFailure("dependency_unavailable:pymupdf") from exc
    try:
        document = fitz.open(context.path)
    except Exception as exc:
        raise ParseFailure("corrupt_pdf") from exc
    blocks, assets = [], []
    total_chars = order = 0
    try:
        if document.needs_pass:
            raise ParseFailure("encrypted_pdf")
        if document.page_count > context.limits.max_pages:
            raise ParseFailure("resource_limit:pages")
        for page_number, page in enumerate(document, start=1):
            page_has_text = False
            for raw in page.get_text("blocks", sort=True):
                if len(raw) > 6 and raw[6] != 0:
                    continue
                text = str(raw[4]).strip()
                if not text:
                    continue
                page_has_text = True
                order += 1
                total_chars += len(text)
                blocks.append(ParsedBlock(element_id(context.source_id, "block", order), order, "text", text, page=page_number, bbox=_bbox(raw)))
                if len(blocks) > context.limits.max_blocks or total_chars > context.limits.max_text_chars:
                    raise ParseFailure("resource_limit:text_blocks")
            if not page_has_text:
                order += 1
                rect = page.rect
                assets.append(ParsedAsset(element_id(context.source_id, "asset", order), order, "page", "ocr_required", page=page_number, bbox=_bbox((rect.x0, rect.y0, rect.x1, rect.y1))))
                if len(assets) > context.limits.max_assets:
                    raise ParseFailure("resource_limit:assets")
        status = ParseStatus.OCR_REQUIRED if assets else ParseStatus.READY
        return finish(context, "pdf_text", status=status, blocks=tuple(blocks), assets=tuple(assets), page_count=document.page_count)
    finally:
        document.close()

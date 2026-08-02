from pathlib import Path

import fitz

from knowledge_pipeline.enterprise.orchestrator import parse_document
from knowledge_pipeline.enterprise.parsed_contracts import ParseStatus
from knowledge_pipeline.enterprise.parsers.base import ParserLimits


def test_pdf_returns_page_blocks_bbox_and_marks_blank_page_for_ocr(tmp_path: Path) -> None:
    path = tmp_path / "mixed.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Market rule 2026")
    document.new_page()
    document.save(path)
    document.close()

    first = parse_document(path, source_id="src_pdf", detected_format="pdf")
    second = parse_document(path, source_id="src_pdf", detected_format="pdf")

    assert first.status is ParseStatus.OCR_REQUIRED
    assert first.page_count == 2
    assert first.blocks[0].page == 1 and first.blocks[0].bbox is not None
    assert first.assets[0].page == 2 and first.assets[0].status == "ocr_required"
    assert all(block.page != 2 for block in first.blocks)
    assert first.to_dict() == second.to_dict()


def test_pdf_corruption_page_limit_and_unsupported_format_fail_closed(tmp_path: Path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not-pdf")
    broken_result = parse_document(broken, source_id="src_broken", detected_format="pdf")
    oversized = parse_document(broken, source_id="src_large", detected_format="pdf", limits=ParserLimits(max_file_bytes=1))
    missing = parse_document(tmp_path / "missing.pdf", source_id="src_missing", detected_format="pdf")
    assert (broken_result.status, broken_result.isolation_reason) == (ParseStatus.QUARANTINED, "corrupt_pdf")
    assert oversized.isolation_reason == "resource_limit:file_bytes"
    assert missing.isolation_reason == "source_unavailable"

    valid = tmp_path / "two.pdf"
    document = fitz.open()
    document.new_page()
    document.new_page()
    document.save(valid)
    document.close()
    limited = parse_document(valid, source_id="src_limit", detected_format="pdf", limits=ParserLimits(max_pages=1))
    unsupported = parse_document(valid, source_id="src_wps", detected_format="wps")
    assert limited.isolation_reason == "resource_limit:pages"
    assert unsupported.isolation_reason == "unsupported_parser_format:wps"

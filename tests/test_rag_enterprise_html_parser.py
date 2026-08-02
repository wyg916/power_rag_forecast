from pathlib import Path

from knowledge_pipeline.enterprise.orchestrator import parse_document
from knowledge_pipeline.enterprise.parsed_contracts import ParseStatus


def test_html_preserves_title_paragraph_table_asset_order(tmp_path: Path) -> None:
    path = tmp_path / "ordered.html"
    path.write_text(
        "<html><head><title>政策标题</title></head><body>"
        "<h1>第一章</h1><p>表格之前</p>"
        "<table><tr><th>名称</th><th>值</th></tr><tr><td>电价</td><td>100</td></tr></table>"
        "<img src='chart.png' alt='价格图'><p>表格之后</p></body></html>",
        encoding="utf-8",
    )
    result = parse_document(path, source_id="src_html", detected_format="html")
    repeated = parse_document(path, source_id="src_html", detected_format="html")
    assert result.status is ParseStatus.READY
    assert [(block.order, block.kind) for block in result.blocks] == [
        (1, "title"), (2, "heading"), (3, "paragraph"), (4, "table"), (6, "paragraph")
    ]
    assert result.tables[0].rows[1] == ("电价", "100")
    assert result.assets[0].order == 5 and result.assets[0].source_ref == "chart.png"
    assert result.to_dict() == repeated.to_dict()


def test_empty_and_invalid_html_are_quarantined(tmp_path: Path) -> None:
    empty = tmp_path / "empty.html"
    empty.write_text("<html><body></body></html>", encoding="utf-8")
    invalid = tmp_path / "invalid.html"
    invalid.write_bytes(b"\xff\xff\xff")
    empty_result = parse_document(empty, source_id="src_empty", detected_format="html")
    invalid_result = parse_document(invalid, source_id="src_invalid", detected_format="html")
    assert (empty_result.status, empty_result.isolation_reason) == (ParseStatus.QUARANTINED, "empty_document")
    assert (invalid_result.status, invalid_result.isolation_reason) == (ParseStatus.QUARANTINED, "invalid_text_encoding")

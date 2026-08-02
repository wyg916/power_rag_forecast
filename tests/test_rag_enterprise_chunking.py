import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from knowledge_pipeline.enterprise.chunk_contracts import CHUNK_BUILD_SCHEMA_VERSION
from knowledge_pipeline.enterprise.chunking import ChunkBuildError, build_candidate
from knowledge_pipeline.enterprise.frozen_export import export_frozen_records
from knowledge_pipeline.enterprise.parsed_contracts import BoundingBox, ParsedAsset, ParsedBlock, ParsedDocument, ParsedTable, ParseStatus


def _document() -> ParsedDocument:
    blocks = (
        ParsedBlock("b1", 1, "heading", "第一章", ("第一章",)),
        ParsedBlock("b2", 2, "paragraph", "甲乙丙丁。" * 12, ("第一章",)),
        ParsedBlock("b3", 3, "table", "", ("第一章",), table_id="t1"),
    )
    table = ParsedTable("t1", 3, (("名称", "数值"), ("电价", "100")), page=2, bbox=BoundingBox(1, 2, 3, 4))
    asset = ParsedAsset(
        "a1", 4, "image", "ready", page=3, bbox=BoundingBox(5, 6, 7, 8),
        source_ref="chart.png", content_hash="b" * 64,
    )
    return ParsedDocument("src_1", str(Path("fixture.docx")), "docx", "a" * 64, "fixture", "1", ParseStatus.READY, blocks, (table,), (asset,))


def _validate_frozen_def(name: str, value: dict) -> None:
    root = Path(__file__).parents[1]
    schema = json.loads((root / "docs/codex/contracts/rag_candidate_corpus_v1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator({"$defs": schema["$defs"], "$ref": f"#/$defs/{name}"}).validate(value)


def test_parent_child_chunking_is_stable_and_preserves_table_and_asset() -> None:
    document = _document()
    first = build_candidate(document, token_counter=len, max_tokens=24)
    second = build_candidate(document, token_counter=len, max_tokens=24)
    paragraph = next(parent for parent in first.parents if parent.block_id == "b2")
    table = next(parent for parent in first.parents if parent.table_id == "t1")
    paragraph_children = [chunk for chunk in first.chunks if chunk.parent_id == paragraph.parent_id]
    assert len(paragraph_children) > 1
    assert paragraph_children[0].content.startswith("标题路径：第一章\n")
    assert "| 名称 | 数值 |" in table.content
    assert table.page == 2 and table.bbox == BoundingBox(1, 2, 3, 4)
    assert table.asset_ids == ("t1",)
    assert all(chunk.table_id == "t1" and chunk.asset_ids == ("t1",) for chunk in first.chunks if chunk.parent_id == table.parent_id)
    assert first.version_id.startswith("ver_")
    assert first.document_id.startswith("doc_")
    assert first.schema_version == CHUNK_BUILD_SCHEMA_VERSION
    assert first.to_json_bytes() == second.to_json_bytes()

    frozen = export_frozen_records(first)
    assert frozen["target_schema_version"] == "rag-candidate-corpus/v1"
    assert frozen["document_id"] == first.document_id
    assert frozen["chunks"][0]["document_id"] == first.document_id
    assert {asset["asset_type"] for asset in frozen["assets"]} == {"table", "image"}
    for chunk in frozen["chunks"]:
        _validate_frozen_def("chunk", chunk)
        _validate_frozen_def("citation", chunk["citation"])
    for asset in frozen["assets"]:
        _validate_frozen_def("asset", asset)


def test_token_counter_is_required_and_fail_closed() -> None:
    document = _document()
    with pytest.raises(ChunkBuildError, match="token_counter_required"):
        build_candidate(document, token_counter=None, max_tokens=24)
    with pytest.raises(ChunkBuildError, match="token_counter_failed"):
        build_candidate(document, token_counter=lambda _: 1 / 0, max_tokens=24)
    with pytest.raises(ChunkBuildError, match="token_counter_invalid"):
        build_candidate(document, token_counter=lambda _: 0, max_tokens=24)


def test_unfinished_asset_fails_and_layout_table_wins_ambiguous_page_link() -> None:
    document = _document()
    discovered = ParsedAsset("pending", 4, "image", "discovered", page=2)
    with pytest.raises(ChunkBuildError, match="asset_not_ready"):
        build_candidate(replace(document, assets=(discovered,)), token_counter=len, max_tokens=24)

    overlapping = ParsedAsset(
        "image_2", 4, "image", "ready", page=2, bbox=BoundingBox(9, 10, 11, 12),
        content_hash="c" * 64,
    )
    build = build_candidate(replace(document, assets=(overlapping,)), token_counter=len, max_tokens=24)
    assert any(asset.asset_id == "image_2" for asset in build.assets)
    assert all("image_2" not in chunk.citation.asset_ids for chunk in build.chunks)
    assert export_frozen_records(build)["assets"]

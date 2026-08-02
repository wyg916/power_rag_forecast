from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .chunk_contracts import ChunkBuildResult
from .citation import citation_errors, text_hash


@dataclass(frozen=True)
class QualityIssue:
    code: str
    entity_id: str


@dataclass(frozen=True)
class CandidateQualityReport:
    ok: bool
    parent_count: int
    chunk_count: int
    issues: tuple[QualityIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_candidate(candidate: ChunkBuildResult) -> CandidateQualityReport:
    issues: list[QualityIssue] = []
    parent_ids = [parent.parent_id for parent in candidate.parents]
    chunk_ids = [chunk.chunk_id for chunk in candidate.chunks]
    asset_ids_list = [asset.asset_id for asset in candidate.assets]
    if not candidate.parents:
        issues.append(QualityIssue("empty_candidate_parents", candidate.source_id))
    if not candidate.chunks:
        issues.append(QualityIssue("empty_candidate_chunks", candidate.source_id))
    if len(set(parent_ids)) != len(parent_ids):
        issues.append(QualityIssue("duplicate_parent_id", candidate.source_id))
    if len(set(chunk_ids)) != len(chunk_ids):
        issues.append(QualityIssue("duplicate_chunk_id", candidate.source_id))
    if len(set(asset_ids_list)) != len(asset_ids_list):
        issues.append(QualityIssue("duplicate_asset_id", candidate.source_id))
    if candidate.document_status == "ocr_required":
        issues.append(QualityIssue("document_ocr_incomplete", candidate.source_id))
    for asset in candidate.assets:
        if asset.status != "ready":
            issues.append(QualityIssue("asset_not_ready", asset.asset_id))
        else:
            if asset.asset_type not in {"image", "table", "formula", "chart"}:
                issues.append(QualityIssue("asset_type_invalid", asset.asset_id))
            if len(asset.content_hash) != 64 or any(char not in "0123456789abcdef" for char in asset.content_hash):
                issues.append(QualityIssue("asset_hash_missing_or_invalid", asset.asset_id))
            if asset.page is None or isinstance(asset.page, bool) or not isinstance(asset.page, int) or asset.page < 1 or asset.bbox is None:
                issues.append(QualityIssue("asset_locator_incomplete", asset.asset_id))
        if asset.version_id != candidate.version_id:
            issues.append(QualityIssue("asset_version_mismatch", asset.asset_id))
    asset_ids = {asset.asset_id for asset in candidate.assets}
    parents = {parent.parent_id: parent for parent in candidate.parents}
    for parent in candidate.parents:
        if not parent.content:
            issues.append(QualityIssue("empty_parent_content", parent.parent_id))
        if parent.content_hash != text_hash(parent.content):
            issues.append(QualityIssue("parent_hash_mismatch", parent.parent_id))
        if any(asset_id not in asset_ids for asset_id in parent.asset_ids):
            issues.append(QualityIssue("parent_asset_missing", parent.parent_id))
    children_by_parent: dict[str, list] = {}
    for chunk in candidate.chunks:
        if not chunk.content or not chunk.citation.quote:
            issues.append(QualityIssue("empty_chunk_content", chunk.chunk_id))
        if chunk.content_hash != text_hash(chunk.content):
            issues.append(QualityIssue("chunk_hash_mismatch", chunk.chunk_id))
        if chunk.token_count <= 0:
            issues.append(QualityIssue("token_count_invalid", chunk.chunk_id))
        if (chunk.source_id, chunk.version_id) != (candidate.source_id, candidate.version_id):
            issues.append(QualityIssue("chunk_identity_mismatch", chunk.chunk_id))
        parent = parents.get(chunk.parent_id)
        if parent is None:
            issues.append(QualityIssue("parent_missing", chunk.chunk_id))
            continue
        children_by_parent.setdefault(parent.parent_id, []).append(chunk)
        expected_prefix = f"标题路径：{' / '.join(chunk.citation.section_path)}\n" if chunk.citation.section_path else ""
        if chunk.content != expected_prefix + chunk.citation.quote:
            issues.append(QualityIssue("chunk_quote_context_mismatch", chunk.chunk_id))
        if chunk.table_id != parent.table_id or chunk.asset_ids != parent.asset_ids:
            issues.append(QualityIssue("chunk_parent_context_mismatch", chunk.chunk_id))
        for code in citation_errors(chunk.citation, parent):
            issues.append(QualityIssue(code, chunk.chunk_id))
    for parent in candidate.parents:
        expected = 0
        children = sorted(children_by_parent.get(parent.parent_id, []), key=lambda item: (item.citation.char_start, item.child_index))
        if not children:
            issues.append(QualityIssue("parent_without_children", parent.parent_id))
            continue
        for child in children:
            if child.citation.char_start != expected:
                issues.append(QualityIssue("child_locator_gap_or_overlap", child.chunk_id))
            expected = child.citation.char_end
        if expected != len(parent.content):
            issues.append(QualityIssue("parent_content_not_fully_covered", parent.parent_id))
    return CandidateQualityReport(not issues, len(candidate.parents), len(candidate.chunks), tuple(issues))

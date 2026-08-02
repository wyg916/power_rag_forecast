from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Callable, Iterable

from .chunk_contracts import ChunkBuildResult
from .chunking import ChunkBuildError
from .contracts import AdmissionStatus, SCHEMA_VERSION, SourceLedgerEntry
from .frozen_export import FrozenExportError
from .ledger import serialize_ledger
from .parsed_contracts import ParsedDocument, ParseStatus
from .quality import validate_candidate


ORCHESTRATION_VERSION = "rag-candidate-orchestration/v1"
FROZEN_MANIFEST_VERSION = "rag-candidate-corpus/v1"
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
ISOLATION_REASON_CODES = frozenset(
    {
        "candidate_quality_failed", "candidate_record_identity_duplicate", "chunk_build_identity_mismatch",
        "chunk_build_quality_failed", "chunk_quality_failed", "citation_asset_cardinality_invalid",
        "document_identity_incomplete", "document_metadata_invalid", "duplicate_table_id", "empty_block",
        "empty_table", "frozen_asset_invalid", "frozen_assets_invalid", "frozen_chunk_invalid",
        "frozen_chunks_empty", "frozen_citation_asset_cardinality_invalid", "frozen_citation_asset_missing",
        "frozen_citation_invalid", "frozen_identity_mismatch", "frozen_record_set_mismatch", "max_tokens_invalid",
        "parsed_content_hash_mismatch", "parsed_document_quarantined", "parsed_not_ready",
        "parsed_source_hash_mismatch", "parsed_source_identity_mismatch", "parsed_transformed_hash_mismatch",
        "table_missing", "token_budget_too_small", "token_counter_failed", "token_counter_invalid",
        "token_counter_required",
    }
)


class CandidateOrchestrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmbeddingProfile:
    provider: str
    model: str
    dimension: int
    model_sha256: str
    sparse_profile: str


@dataclass(frozen=True)
class DocumentMetadata:
    source_id: str
    title: str
    domain: str
    effective_from: str
    effective_to: str | None = None
    visibility: str = "tenant"
    roles: tuple[str, ...] = ()
    users: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedSourceInput:
    source_id: str
    source_sha256: str
    document: ParsedDocument
    transformed_sha256: str = ""


@dataclass(frozen=True)
class CandidateCorpusArtifact:
    value: dict[str, Any]

    def to_json_bytes(self) -> bytes:
        return _canonical_bytes(self.value) + b"\n"

    @property
    def candidate_manifest(self) -> dict[str, Any]:
        return self.value["candidate_manifest"]


CandidateBuilder = Callable[[ParsedDocument], ChunkBuildResult]
FrozenExporter = Callable[[ChunkBuildResult], dict[str, Any]]


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _valid_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return False
    return parsed.tzinfo is not None


def _validate_profile(profile: EmbeddingProfile) -> dict[str, Any]:
    if (
        profile.provider != "sentence_transformers"
        or profile.model != "BAAI/bge-large-zh-v1.5"
        or profile.dimension != 1024
        or not SHA256_PATTERN.fullmatch(profile.model_sha256)
        or not profile.sparse_profile
        or len(profile.sparse_profile) > 128
    ):
        raise CandidateOrchestrationError("embedding_profile_not_approved")
    return asdict(profile)


def _ordered_ledger(entries: Iterable[SourceLedgerEntry]) -> tuple[SourceLedgerEntry, ...]:
    ordered = tuple(sorted(entries, key=lambda item: (item.relative_path.casefold(), item.relative_path, item.source_id)))
    if len(ordered) != 83:
        raise CandidateOrchestrationError(f"ledger_count_mismatch:{len(ordered)}")
    ids = [entry.source_id for entry in ordered]
    paths = [entry.relative_path for entry in ordered]
    if len(set(ids)) != len(ids) or len(set(paths)) != len(paths):
        raise CandidateOrchestrationError("ledger_identity_duplicate")
    by_id = {entry.source_id: entry for entry in ordered}
    ready_hashes: set[str] = set()
    for entry in ordered:
        if entry.schema_version != SCHEMA_VERSION or not ID_PATTERN.fullmatch(entry.source_id):
            raise CandidateOrchestrationError("ledger_contract_invalid")
        if not SHA256_PATTERN.fullmatch(entry.sha256):
            raise CandidateOrchestrationError(f"ledger_hash_invalid:{entry.source_id}")
        if entry.admission_status is AdmissionStatus.READY:
            if entry.sha256 in ready_hashes:
                raise CandidateOrchestrationError("ledger_ready_content_duplicate")
            ready_hashes.add(entry.sha256)
            if entry.isolation_reason or entry.duplicate_of_source_id or entry.duplicate_of_path:
                raise CandidateOrchestrationError("ledger_ready_terminal_invalid")
        elif entry.admission_status is AdmissionStatus.DUPLICATE:
            canonical = by_id.get(entry.duplicate_of_source_id)
            if (
                canonical is None
                or canonical.admission_status not in {AdmissionStatus.READY, AdmissionStatus.QUARANTINED}
                or canonical.sha256 != entry.sha256
                or canonical.relative_path != entry.duplicate_of_path
                or not entry.isolation_reason
            ):
                raise CandidateOrchestrationError(f"ledger_duplicate_canonical_invalid:{entry.source_id}")
        elif not entry.isolation_reason:
            raise CandidateOrchestrationError(f"ledger_isolation_reason_missing:{entry.source_id}")
    return ordered


def _metadata_record(metadata: DocumentMetadata, build: ChunkBuildResult, entry: SourceLedgerEntry) -> dict[str, Any]:
    roles, users = tuple(sorted(metadata.roles)), tuple(sorted(metadata.users))
    if (
        metadata.source_id != entry.source_id
        or not metadata.title.strip()
        or not metadata.domain.strip()
        or not _valid_timestamp(metadata.effective_from)
        or (metadata.effective_to is not None and not _valid_timestamp(metadata.effective_to))
        or metadata.visibility not in {"tenant", "restricted"}
        or len(set(roles)) != len(roles)
        or len(set(users)) != len(users)
        or any(not ID_PATTERN.fullmatch(value) for value in roles + users)
        or (metadata.visibility == "restricted" and not (roles or users))
    ):
        raise CandidateOrchestrationError("document_metadata_invalid")
    return {
        "document_id": build.document_id,
        "version_id": build.version_id,
        "source_id": entry.source_id,
        "source_sha256": entry.sha256,
        "title": metadata.title.strip(),
        "domain": metadata.domain.strip(),
        "status": "ready",
        "effective_from": metadata.effective_from,
        "effective_to": metadata.effective_to,
        "acl": {"visibility": metadata.visibility, "roles": list(roles), "users": list(users)},
    }


def _validate_parsed(source: ParsedSourceInput, entry: SourceLedgerEntry) -> None:
    document = source.document
    if source.source_id != entry.source_id or document.source_id != entry.source_id:
        raise CandidateOrchestrationError("parsed_source_identity_mismatch")
    if source.source_sha256 != entry.sha256:
        raise CandidateOrchestrationError("parsed_source_hash_mismatch")
    if source.transformed_sha256:
        if not SHA256_PATTERN.fullmatch(source.transformed_sha256) or document.content_hash != source.transformed_sha256:
            raise CandidateOrchestrationError("parsed_transformed_hash_mismatch")
    elif document.content_hash != entry.sha256:
        raise CandidateOrchestrationError("parsed_content_hash_mismatch")
    if document.status is not ParseStatus.READY:
        reason = document.isolation_reason or document.status.value
        raise CandidateOrchestrationError(f"parsed_not_ready:{reason}")


def _validate_frozen(build: ChunkBuildResult, frozen: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    report = validate_candidate(build)
    if not report.ok:
        raise CandidateOrchestrationError("chunk_quality_failed:" + report.issues[0].code)
    if (
        set(frozen) != {"target_schema_version", "document_id", "version_id", "chunks", "assets"}
        or frozen.get("target_schema_version") != FROZEN_MANIFEST_VERSION
        or frozen.get("document_id") != build.document_id
        or frozen.get("version_id") != build.version_id
    ):
        raise CandidateOrchestrationError("frozen_identity_mismatch")
    chunks, assets = frozen.get("chunks"), frozen.get("assets")
    if not isinstance(chunks, list) or not chunks:
        raise CandidateOrchestrationError("frozen_chunks_empty")
    if not isinstance(assets, list):
        raise CandidateOrchestrationError("frozen_assets_invalid")
    build_chunk_ids = {chunk.chunk_id for chunk in build.chunks}
    build_asset_ids = {asset.asset_id for asset in build.assets}
    if {item.get("chunk_id") for item in chunks} != build_chunk_ids or {item.get("asset_id") for item in assets} != build_asset_ids:
        raise CandidateOrchestrationError("frozen_record_set_mismatch")
    for chunk in chunks:
        content, citation = chunk.get("content"), chunk.get("citation")
        expected = next(item for item in build.chunks if item.chunk_id == chunk.get("chunk_id"))
        locator = expected.citation
        if len(locator.asset_ids) > 1:
            raise CandidateOrchestrationError("frozen_citation_asset_cardinality_invalid")
        expected_citation = {
            "version_id": locator.version_id,
            "page": locator.page,
            "section_path": list(locator.section_path),
            "char_start": locator.char_start,
            "char_end": locator.char_end,
            "bbox": None if locator.bbox is None else [locator.bbox.x0, locator.bbox.y0, locator.bbox.x1, locator.bbox.y1],
            "asset_id": locator.asset_ids[0] if locator.asset_ids else None,
            "quote": locator.quote,
            "content_hash": locator.content_hash,
        }
        expected_chunk = {
            "chunk_id": expected.chunk_id,
            "document_id": build.document_id,
            "version_id": expected.version_id,
            "parent_chunk_id": expected.parent_id,
            "content": expected.content,
            "content_hash": expected.content_hash,
            "token_count": expected.token_count,
            "citation": expected_citation,
        }
        if (
            chunk != expected_chunk
            or chunk.get("document_id") != build.document_id
            or chunk.get("version_id") != build.version_id
            or not isinstance(content, str)
            or hashlib.sha256(content.encode("utf-8")).hexdigest() != chunk.get("content_hash")
            or not isinstance(citation, dict)
            or citation.get("version_id") != build.version_id
        ):
            raise CandidateOrchestrationError("frozen_chunk_invalid")
        quote = citation.get("quote")
        start, end = citation.get("char_start"), citation.get("char_end")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < 0
            or end <= start
            or not isinstance(quote, str)
            or hashlib.sha256(quote.encode("utf-8")).hexdigest() != citation.get("content_hash")
        ):
            raise CandidateOrchestrationError("frozen_citation_invalid")
        asset_id = citation.get("asset_id")
        if asset_id is not None and asset_id not in build_asset_ids:
            raise CandidateOrchestrationError("frozen_citation_asset_missing")
    for asset in assets:
        bbox = asset.get("bbox")
        expected = next(item for item in build.assets if item.asset_id == asset.get("asset_id"))
        expected_asset = {
            "asset_id": expected.asset_id,
            "version_id": expected.version_id,
            "asset_type": expected.asset_type,
            "content_hash": expected.content_hash,
            "page": expected.page,
            "bbox": None if expected.bbox is None else [expected.bbox.x0, expected.bbox.y0, expected.bbox.x1, expected.bbox.y1],
        }
        if (
            asset != expected_asset
            or asset.get("version_id") != build.version_id
            or asset.get("asset_type") not in {"image", "table", "formula", "chart"}
            or not SHA256_PATTERN.fullmatch(str(asset.get("content_hash") or ""))
            or not isinstance(asset.get("page"), int)
            or isinstance(asset.get("page"), bool)
            or asset["page"] < 1
            or not isinstance(bbox, list)
            or len(bbox) != 4
            or bbox[0] > bbox[2]
            or bbox[1] > bbox[3]
        ):
            raise CandidateOrchestrationError("frozen_asset_invalid")
    return chunks, assets


def _reason(exc: Exception) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", str(exc).partition(":")[0]).strip("_")
    if value in ISOLATION_REASON_CODES:
        return value
    if isinstance(exc, ChunkBuildError):
        return "chunk_build_rejected"
    if isinstance(exc, FrozenExportError):
        return "frozen_export_rejected"
    return "candidate_contract_rejected"


def build_candidate_corpus(
    *,
    ledger_entries: Iterable[SourceLedgerEntry],
    parsed_sources: dict[str, ParsedSourceInput],
    document_metadata: dict[str, DocumentMetadata],
    candidate_release_id: str,
    tenant_id: str,
    created_at: str,
    embedding_profile: EmbeddingProfile,
    candidate_builder: CandidateBuilder,
    frozen_exporter: FrozenExporter,
) -> CandidateCorpusArtifact:
    if tenant_id != "default" or not ID_PATTERN.fullmatch(candidate_release_id) or not _valid_timestamp(created_at):
        raise CandidateOrchestrationError("candidate_identity_invalid")
    profile = _validate_profile(embedding_profile)
    ordered = _ordered_ledger(ledger_entries)
    ready_ids = {entry.source_id for entry in ordered if entry.admission_status is AdmissionStatus.READY}
    if set(parsed_sources) - ready_ids:
        raise CandidateOrchestrationError("parsed_source_not_canonical_ready")
    if set(document_metadata) - ready_ids:
        raise CandidateOrchestrationError("metadata_source_not_canonical_ready")

    documents: list[dict] = []
    versions: list[dict] = []
    chunks: list[dict] = []
    assets: list[dict] = []
    isolations: list[dict] = []
    duplicates: list[dict] = []
    document_ids: set[str] = set()
    version_ids: set[str] = set()
    chunk_ids: set[str] = set()
    asset_ids: set[str] = set()

    for entry in ordered:
        if entry.admission_status is AdmissionStatus.DUPLICATE:
            duplicates.append(
                {"source_id": entry.source_id, "canonical_source_id": entry.duplicate_of_source_id, "source_sha256": entry.sha256}
            )
            continue
        if entry.admission_status is not AdmissionStatus.READY:
            isolations.append(
                {"source_id": entry.source_id, "ledger_status": entry.admission_status.value, "reason": entry.isolation_reason}
            )
            continue
        source = parsed_sources.get(entry.source_id)
        metadata = document_metadata.get(entry.source_id)
        if source is None or metadata is None:
            missing = "parsed_source_missing" if source is None else "document_metadata_missing"
            isolations.append({"source_id": entry.source_id, "ledger_status": "ready", "reason": missing})
            continue
        try:
            _validate_parsed(source, entry)
        except CandidateOrchestrationError as exc:
            isolations.append({"source_id": entry.source_id, "ledger_status": "ready", "reason": _reason(exc)})
            continue
        except Exception:
            raise CandidateOrchestrationError("candidate_validation_internal_error") from None

        try:
            build = candidate_builder(source.document)
        except ChunkBuildError as exc:
            isolations.append({"source_id": entry.source_id, "ledger_status": "ready", "reason": _reason(exc)})
            continue
        except Exception:
            raise CandidateOrchestrationError("candidate_builder_internal_error") from None

        try:
            if (
                build.source_id != entry.source_id
                or build.document_hash != source.document.content_hash
                or build.document_status != "ready"
            ):
                raise CandidateOrchestrationError("chunk_build_identity_mismatch")
        except CandidateOrchestrationError as exc:
            isolations.append({"source_id": entry.source_id, "ledger_status": "ready", "reason": _reason(exc)})
            continue
        except Exception:
            raise CandidateOrchestrationError("candidate_builder_contract_internal_error") from None

        try:
            frozen = frozen_exporter(build)
        except FrozenExportError as exc:
            isolations.append({"source_id": entry.source_id, "ledger_status": "ready", "reason": _reason(exc)})
            continue
        except Exception:
            raise CandidateOrchestrationError("frozen_exporter_internal_error") from None

        try:
            source_chunks, source_assets = _validate_frozen(build, frozen)
            document = _metadata_record(metadata, build, entry)
            current_chunks = {item["chunk_id"] for item in source_chunks}
            current_assets = {item["asset_id"] for item in source_assets}
            if (
                build.document_id in document_ids
                or build.version_id in version_ids
                or current_chunks & chunk_ids
                or current_assets & asset_ids
            ):
                raise CandidateOrchestrationError("candidate_record_identity_duplicate")
        except CandidateOrchestrationError as exc:
            isolations.append({"source_id": entry.source_id, "ledger_status": "ready", "reason": _reason(exc)})
            continue
        except Exception:
            raise CandidateOrchestrationError("candidate_contract_internal_error") from None
        documents.append(document)
        versions.append(
            {
                "source_id": entry.source_id,
                "document_id": build.document_id,
                "version_id": build.version_id,
                "source_sha256": entry.sha256,
                "content_sha256": build.document_hash,
                "transformed": bool(source.transformed_sha256),
            }
        )
        chunks.extend(source_chunks)
        assets.extend(source_assets)
        document_ids.add(build.document_id)
        version_ids.add(build.version_id)
        chunk_ids.update(current_chunks)
        asset_ids.update(current_assets)

    documents.sort(key=lambda item: (item["source_id"], item["version_id"]))
    versions.sort(key=lambda item: (item["source_id"], item["version_id"]))
    chunks.sort(key=lambda item: (item["document_id"], item["chunk_id"]))
    assets.sort(key=lambda item: (item["version_id"], item["asset_id"]))
    isolations.sort(key=lambda item: item["source_id"])
    duplicates.sort(key=lambda item: item["source_id"])
    status_counts = Counter(entry.admission_status.value for entry in ordered)
    complete_status_counts = {status.value: status_counts[status.value] for status in AdmissionStatus}
    ledger_hash = hashlib.sha256(serialize_ledger(ordered)).hexdigest()
    frozen_base = {
        "manifest_version": FROZEN_MANIFEST_VERSION,
        "candidate_release_id": candidate_release_id,
        "tenant_id": tenant_id,
        "release_status": "candidate",
        "created_at": created_at,
        "embedding_profile": profile,
        "ledger_summary": {
            "total": len(ordered),
            "ready": status_counts["ready"],
            "quarantined": status_counts["quarantined"],
            "duplicate": status_counts["duplicate"],
            "corrupt": status_counts["corrupt"],
        },
        "documents": documents,
        "chunks": chunks,
        "assets": assets,
    }
    candidate_manifest = frozen_base | {"corpus_sha256": _hash(frozen_base)}
    outer = {
        "orchestration_version": ORCHESTRATION_VERSION,
        "candidate_release_id": candidate_release_id,
        "tenant_id": tenant_id,
        "created_at": created_at,
        "source_ledger": {"schema_version": SCHEMA_VERSION, "sha256": ledger_hash, "status_counts": complete_status_counts},
        "embedding_profile": profile,
        "versions": versions,
        "counts": {
            "ledger": len(ordered), "documents": len(documents), "chunks": len(chunks), "assets": len(assets),
            "duplicates": len(duplicates), "isolations": len(isolations),
        },
        "duplicates": duplicates,
        "isolations": isolations,
        "candidate_manifest": candidate_manifest,
    }
    return CandidateCorpusArtifact(outer | {"artifact_sha256": _hash(outer)})

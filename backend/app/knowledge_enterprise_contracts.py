from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CONTRACT_VERSION = "rag-enterprise-api/v1"
SHA256_PATTERN = r"^[a-f0-9]{64}$"
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


class IngestionState(str, Enum):
    DRAFT = "draft"
    PARSING = "parsing"
    VALIDATING = "validating"
    READY = "ready"
    QUARANTINED = "quarantined"
    CORRUPT = "corrupt"


class ReleaseState(str, Enum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    ROLLED_BACK = "rolled_back"


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AccessPolicyContract(StrictContract):
    visibility: Literal["tenant", "restricted"]
    roles: list[str] = Field(default_factory=list)
    users: list[str] = Field(default_factory=list)

    @field_validator("roles", "users")
    @classmethod
    def _unique_identifiers(cls, values: list[str]) -> list[str]:
        cleaned = sorted(set(values))
        if len(cleaned) != len(values) or any(not value for value in cleaned):
            raise ValueError("acl_identifiers_invalid")
        return cleaned

    @model_validator(mode="after")
    def _restricted_has_subject(self) -> "AccessPolicyContract":
        if self.visibility == "restricted" and not (self.roles or self.users):
            raise ValueError("restricted_acl_subject_required")
        return self


class IngestionCreateRequest(StrictContract):
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(ge=1, le=512 * 1024 * 1024)
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    idempotency_key: str = Field(min_length=8, max_length=256)
    acl: AccessPolicyContract


class ComponentProgressContract(StrictContract):
    component: Literal["parse", "ocr_vlm", "validate", "embedding"]
    status: Literal["pending", "running", "succeeded", "failed", "skipped"]
    processed: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    reason_code: str = Field(default="", max_length=128)


class IngestionContract(StrictContract):
    ingestion_id: str = Field(pattern=ID_PATTERN)
    tenant_id: Literal["default"]
    status: IngestionState
    source_id: str = Field(pattern=ID_PATTERN)
    version_id: str | None = Field(default=None, pattern=ID_PATTERN)
    progress: list[ComponentProgressContract] = Field(default_factory=list)
    isolation_reason: str = Field(default="", max_length=256)
    run_id: str = Field(pattern=ID_PATTERN)
    trace_id: str = Field(pattern=ID_PATTERN)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _state_has_required_facts(self) -> "IngestionContract":
        if self.status is IngestionState.READY and self.version_id is None:
            raise ValueError("ready_version_required")
        if self.status in {IngestionState.QUARANTINED, IngestionState.CORRUPT} and not self.isolation_reason:
            raise ValueError("isolation_reason_required")
        return self


class EmbeddingProfileContract(StrictContract):
    provider: Literal["sentence_transformers"]
    model: Literal["BAAI/bge-large-zh-v1.5"]
    version: str = Field(min_length=1, max_length=128)
    dimension: Literal[1024]
    sparse_profile: str = Field(min_length=1, max_length=128)


class ReleaseCreateRequest(StrictContract):
    release_id: str = Field(pattern=ID_PATTERN)
    source_ledger_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    embedding_profile: EmbeddingProfileContract
    idempotency_key: str = Field(min_length=8, max_length=256)


class GateResultContract(StrictContract):
    gate: str = Field(pattern=ID_PATTERN)
    passed: bool
    metric: float | int | None = None
    threshold: float | int | None = None
    reason_code: str = Field(default="", max_length=128)


class ReleaseContract(StrictContract):
    release_id: str = Field(pattern=ID_PATTERN)
    tenant_id: Literal["default"]
    status: ReleaseState
    collection: str = Field(pattern=r"^rag_chunks_[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    alias: Literal["rag_chunks_current"]
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    embedding_profile: EmbeddingProfileContract
    gates: list[GateResultContract] = Field(default_factory=list)
    run_id: str = Field(pattern=ID_PATTERN)
    trace_id: str = Field(pattern=ID_PATTERN)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _collection_matches_release(self) -> "ReleaseContract":
        if self.collection != f"rag_chunks_{self.release_id}":
            raise ValueError("release_collection_mismatch")
        return self


class CitationContract(StrictContract):
    document_id: str = Field(pattern=ID_PATTERN)
    version_id: str = Field(pattern=ID_PATTERN)
    chunk_id: str = Field(pattern=ID_PATTERN)
    release_id: str = Field(pattern=ID_PATTERN)
    page: int | None = Field(default=None, ge=1)
    section_path: list[str] = Field(default_factory=list)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    bbox: tuple[float, float, float, float] | None = None
    asset_id: str | None = Field(default=None, pattern=ID_PATTERN)
    quote: str = Field(min_length=1)
    content_hash: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def _valid_locator(self) -> "CitationContract":
        if self.char_end <= self.char_start:
            raise ValueError("citation_offsets_invalid")
        if self.bbox is not None:
            x0, y0, x1, y1 = self.bbox
            if self.page is None or x0 > x1 or y0 > y1:
                raise ValueError("citation_bbox_invalid")
        return self


class AssetContract(StrictContract):
    asset_id: str = Field(pattern=ID_PATTERN)
    tenant_id: Literal["default"]
    version_id: str = Field(pattern=ID_PATTERN)
    asset_type: Literal["image", "table", "formula", "chart"]
    status: Literal["discovered", "ocr_required", "ready", "quarantined"]
    content_hash: str = Field(pattern=SHA256_PATTERN)
    page: int = Field(ge=1)
    bbox: tuple[float, float, float, float]

    @field_validator("bbox")
    @classmethod
    def _bbox_is_ordered(
        cls, value: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        if value[0] > value[2] or value[1] > value[3]:
            raise ValueError("asset_bbox_invalid")
        return value


class RetrievalRunContract(StrictContract):
    run_id: str = Field(pattern=ID_PATTERN)
    trace_id: str = Field(pattern=ID_PATTERN)
    tenant_id: Literal["default"]
    release_id: str = Field(pattern=ID_PATTERN)
    user_id: str = Field(pattern=ID_PATTERN)
    acl_fingerprint: str = Field(pattern=SHA256_PATTERN)
    query_sha256: str = Field(pattern=SHA256_PATTERN)
    status: Literal["available", "unavailable", "denied"]
    reason_code: str = Field(default="", max_length=128)
    stage_scores: dict[str, list[float]] = Field(default_factory=dict)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    citations: list[CitationContract] = Field(default_factory=list)

    @model_validator(mode="after")
    def _result_is_coherent(self) -> "RetrievalRunContract":
        if self.status == "available" and not self.citations:
            raise ValueError("available_citation_required")
        if self.status != "available" and not self.reason_code:
            raise ValueError("unavailable_reason_required")
        return self


class QAEvaluationContract(StrictContract):
    evaluation_id: str = Field(pattern=ID_PATTERN)
    tenant_id: Literal["default"]
    release_id: str = Field(pattern=ID_PATTERN)
    question_id: str = Field(pattern=ID_PATTERN)
    passed: bool
    confidence: float = Field(ge=0.0, le=1.0)
    citations: list[CitationContract] = Field(default_factory=list)
    latency_ms: float = Field(ge=0.0)
    run_id: str = Field(pattern=ID_PATTERN)
    trace_id: str = Field(pattern=ID_PATTERN)

    @field_validator("confidence", mode="before")
    @classmethod
    def _confidence_is_numeric(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("confidence_must_be_numeric")
        return value

    @model_validator(mode="after")
    def _passed_has_citation(self) -> "QAEvaluationContract":
        if self.passed and not self.citations:
            raise ValueError("passed_citation_required")
        return self


class EnterpriseErrorContract(StrictContract):
    code: str = Field(pattern=ID_PATTERN)
    status: Literal["unavailable", "denied", "conflict", "invalid"]
    message: str = Field(min_length=1, max_length=512)
    release_id: str | None = Field(default=None, pattern=ID_PATTERN)
    run_id: str | None = Field(default=None, pattern=ID_PATTERN)
    trace_id: str | None = Field(default=None, pattern=ID_PATTERN)
    retryable: bool = False


SCHEMA_MODELS = (
    IngestionCreateRequest,
    IngestionContract,
    ReleaseCreateRequest,
    ReleaseContract,
    CitationContract,
    AssetContract,
    RetrievalRunContract,
    QAEvaluationContract,
    EnterpriseErrorContract,
)


def contract_schema_bundle() -> dict[str, Any]:
    schemas = {model.__name__: model.model_json_schema() for model in SCHEMA_MODELS}
    canonical = json.dumps(
        schemas, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "contract_version": CONTRACT_VERSION,
        "schema_sha256": sha256(canonical).hexdigest(),
        "schemas": schemas,
    }

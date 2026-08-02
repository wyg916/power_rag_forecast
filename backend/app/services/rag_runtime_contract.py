from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


ENTERPRISE_PROFILES = {"enterprise", "enterprise_r1", "rag-r1", "rag_r1"}
ENTERPRISE_EMBEDDING_PROVIDERS = {"bge", "sentence_transformers", "sentence_transformer"}
ENTERPRISE_EMBEDDING_MODELS = {"bge-large-zh-v1.5", "baai/bge-large-zh-v1.5"}
ENTERPRISE_RERANK_PROVIDERS = {"bge", "bge_reranker", "transformers", "local_bge"}
ENTERPRISE_RERANK_MODELS = {"bge-reranker-v2-m3", "baai/bge-reranker-v2-m3"}
DISABLED_VALUES = {"", "0", "false", "no", "none", "off", "disabled"}
ENABLED_VALUES = {"1", "true", "yes", "on"}
RELEASE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class RuntimeContractError(RuntimeError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        self.issues = issues
        super().__init__("rag_runtime_unavailable:" + ",".join(issues))


def _normalized(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _model_name(env: Mapping[str, str], name_key: str, model_key: str, path_key: str) -> str:
    explicit = str(env.get(name_key, "") or env.get(model_key, "")).strip()
    if explicit:
        return explicit.lower().replace("\\", "/")
    path_value = str(env.get(path_key, "")).strip()
    return Path(path_value).name.lower() if path_value else ""


def _strict_bool(env: Mapping[str, str], key: str, default: bool) -> tuple[bool, bool]:
    raw = str(env.get(key, "")).strip().lower()
    if not raw:
        return default, True
    if raw in ENABLED_VALUES:
        return True, True
    if raw in DISABLED_VALUES:
        return False, True
    return default, False


def enterprise_mode(env: Mapping[str, str] | None = None) -> bool:
    values = env if env is not None else os.environ
    profile = str(values.get("RAG_PROFILE", "")).strip().lower()
    app_env = str(values.get("APP_ENV", values.get("ENV", ""))).strip().lower()
    return profile in ENTERPRISE_PROFILES or app_env in {"prod", "production"}


@dataclass(frozen=True)
class RetrievalContext:
    tenant_id: str
    user_id: str
    roles: tuple[str, ...]
    acl_fingerprint: str
    release_id: str
    run_id: str = ""
    trace_id: str = ""

    def issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        if not self.tenant_id:
            issues.append("tenant_id_missing")
        if not self.user_id:
            issues.append("user_id_missing")
        if not self.roles:
            issues.append("roles_missing")
        if not self.acl_fingerprint:
            issues.append("acl_fingerprint_missing")
        if not RELEASE_PATTERN.fullmatch(self.release_id or ""):
            issues.append("release_id_invalid")
        return tuple(issues)

    def require_valid(self) -> None:
        if issues := self.issues():
            raise RuntimeContractError(issues)


@dataclass(frozen=True)
class EmbeddingProfile:
    provider: str
    model: str
    version: str
    expected_version: str
    dimensions: int
    expected_dimensions: int
    model_path_configured: bool
    model_path_exists: bool
    model_path_readable: bool
    fallback_enabled: bool


@dataclass(frozen=True)
class RerankProfile:
    provider: str
    model: str
    version: str
    expected_version: str
    enabled: bool
    model_path_configured: bool
    model_path_exists: bool
    model_path_readable: bool
    fallback_enabled: bool


@dataclass(frozen=True)
class ReleaseIdentity:
    release_id: str
    collection: str
    alias: str

    def issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        if not RELEASE_PATTERN.fullmatch(self.release_id or ""):
            issues.append("release_id_invalid")
        expected_collection = f"rag_chunks_{self.release_id}" if self.release_id else ""
        if not self.collection or self.collection != expected_collection:
            issues.append("release_collection_mismatch")
        if self.alias != "rag_chunks_current":
            issues.append("release_alias_invalid")
        return tuple(issues)


@dataclass(frozen=True)
class CitationLocator:
    version_id: str
    page: int | None
    section_path: tuple[str, ...]
    char_start: int
    char_end: int
    content_hash: str
    bbox: tuple[float, float, float, float] | None = None
    asset_id: str = ""

    def issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        if not self.version_id:
            issues.append("citation_version_missing")
        if self.page is not None and self.page < 1:
            issues.append("citation_page_invalid")
        if self.char_start < 0 or self.char_end <= self.char_start:
            issues.append("citation_offsets_invalid")
        if not SHA256_PATTERN.fullmatch((self.content_hash or "").lower()):
            issues.append("citation_hash_invalid")
        if self.bbox is not None and (
            len(self.bbox) != 4
            or self.bbox[0] > self.bbox[2]
            or self.bbox[1] > self.bbox[3]
        ):
            issues.append("citation_bbox_invalid")
        return tuple(issues)

    def require_valid(self) -> None:
        if issues := self.issues():
            raise RuntimeContractError(issues)


@dataclass(frozen=True)
class RuntimeContractStatus:
    enterprise: bool
    embedding: EmbeddingProfile
    reranker: RerankProfile
    release: ReleaseIdentity
    issues: tuple[str, ...]

    @property
    def available(self) -> bool:
        return not self.issues

    def require_available(self) -> None:
        if self.issues:
            raise RuntimeContractError(self.issues)


def runtime_contract_status(env: Mapping[str, str] | None = None) -> RuntimeContractStatus:
    values = env if env is not None else os.environ
    enterprise = enterprise_mode(values)

    embedding_path_value = str(values.get("RAG_EMBEDDING_MODEL_PATH", "")).strip()
    embedding_path = Path(embedding_path_value) if embedding_path_value else None
    embedding_fallback, embedding_fallback_valid = _strict_bool(
        values, "RAG_EMBEDDING_ALLOW_FALLBACK", False
    )
    embedding_fallback_provider = str(
        values.get("RAG_EMBEDDING_FALLBACK_PROVIDER", "")
    ).strip().lower()
    try:
        dimensions = int(str(values.get("RAG_EMBEDDING_DIM", "")).strip() or 0)
    except ValueError:
        dimensions = 0
    try:
        expected_dimensions = int(
            str(values.get("RAG_EMBEDDING_EXPECTED_DIM", "")).strip() or 0
        )
    except ValueError:
        expected_dimensions = 0
    embedding = EmbeddingProfile(
        provider=_normalized(str(values.get("RAG_EMBEDDING_PROVIDER", ""))),
        model=_model_name(
            values,
            "RAG_EMBEDDING_MODEL_NAME",
            "RAG_EMBEDDING_MODEL",
            "RAG_EMBEDDING_MODEL_PATH",
        ),
        version=str(values.get("RAG_EMBEDDING_VERSION", "")).strip(),
        expected_version=str(
            values.get("RAG_EMBEDDING_EXPECTED_VERSION", "")
        ).strip(),
        dimensions=dimensions,
        expected_dimensions=expected_dimensions,
        model_path_configured=bool(embedding_path_value),
        model_path_exists=bool(embedding_path and embedding_path.is_dir()),
        model_path_readable=bool(
            embedding_path and embedding_path.is_dir() and os.access(embedding_path, os.R_OK)
        ),
        fallback_enabled=embedding_fallback
        or embedding_fallback_provider not in DISABLED_VALUES,
    )

    rerank_path_value = str(values.get("RAG_RERANK_MODEL_PATH", "")).strip()
    rerank_path = Path(rerank_path_value) if rerank_path_value else None
    rerank_enabled, rerank_enabled_valid = _strict_bool(values, "RAG_RERANK_ENABLED", True)
    rerank_fallback_value = str(values.get("RAG_RERANK_FALLBACK_PROVIDER", "")).strip().lower()
    reranker = RerankProfile(
        provider=_normalized(str(values.get("RAG_RERANK_PROVIDER", ""))),
        model=_model_name(
            values,
            "RAG_RERANK_MODEL_NAME",
            "RAG_RERANK_MODEL",
            "RAG_RERANK_MODEL_PATH",
        ),
        version=str(values.get("RAG_RERANK_VERSION", "")).strip(),
        expected_version=str(
            values.get("RAG_RERANK_EXPECTED_VERSION", "")
        ).strip(),
        enabled=rerank_enabled,
        model_path_configured=bool(rerank_path_value),
        model_path_exists=bool(rerank_path and rerank_path.is_dir()),
        model_path_readable=bool(
            rerank_path and rerank_path.is_dir() and os.access(rerank_path, os.R_OK)
        ),
        fallback_enabled=rerank_fallback_value not in DISABLED_VALUES,
    )
    release = ReleaseIdentity(
        release_id=str(values.get("RAG_RELEASE_ID", "")).strip(),
        collection=str(values.get("RAG_QDRANT_COLLECTION", "")).strip(),
        alias=str(values.get("RAG_QDRANT_ALIAS", "")).strip(),
    )

    issues: list[str] = []
    if enterprise:
        rag_enabled, rag_enabled_valid = _strict_bool(values, "RAG_ENABLED", True)
        file_fallback, file_fallback_valid = _strict_bool(
            values, "RAG_FILE_FALLBACK_ENABLED", False
        )
        if not rag_enabled_valid or not rag_enabled:
            issues.append("rag_disabled_or_invalid")
        if embedding.provider not in ENTERPRISE_EMBEDDING_PROVIDERS:
            issues.append("embedding_provider_invalid")
        if embedding.model not in ENTERPRISE_EMBEDDING_MODELS:
            issues.append("embedding_model_invalid")
        if not embedding.version:
            issues.append("embedding_version_missing")
        if not embedding.expected_version:
            issues.append("embedding_expected_version_missing")
        if (
            embedding.version
            and embedding.expected_version
            and embedding.version != embedding.expected_version
        ):
            issues.append("embedding_version_mismatch")
        if embedding.dimensions != 1024 or embedding.expected_dimensions != 1024:
            issues.append("embedding_dimension_invalid")
        if not embedding.model_path_configured or not embedding.model_path_exists:
            issues.append("embedding_model_path_unavailable")
        elif not embedding.model_path_readable:
            issues.append("embedding_model_path_unreadable")
        if not embedding_fallback_valid or embedding.fallback_enabled:
            issues.append("embedding_fallback_forbidden")
        if reranker.provider not in ENTERPRISE_RERANK_PROVIDERS:
            issues.append("rerank_provider_invalid")
        if reranker.model not in ENTERPRISE_RERANK_MODELS:
            issues.append("rerank_model_invalid")
        if not reranker.version:
            issues.append("rerank_version_missing")
        if not reranker.expected_version:
            issues.append("rerank_expected_version_missing")
        if (
            reranker.version
            and reranker.expected_version
            and reranker.version != reranker.expected_version
        ):
            issues.append("rerank_version_mismatch")
        if not rerank_enabled_valid or not reranker.enabled:
            issues.append("rerank_disabled_or_invalid")
        if not reranker.model_path_configured or not reranker.model_path_exists:
            issues.append("rerank_model_path_unavailable")
        elif not reranker.model_path_readable:
            issues.append("rerank_model_path_unreadable")
        if reranker.fallback_enabled:
            issues.append("rerank_fallback_forbidden")
        if not file_fallback_valid or file_fallback:
            issues.append("file_fallback_forbidden")
        issues.extend(release.issues())

    return RuntimeContractStatus(
        enterprise=enterprise,
        embedding=embedding,
        reranker=reranker,
        release=release,
        issues=tuple(dict.fromkeys(issues)),
    )

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services import embedding_service, rerank_service
from backend.app.services.rag_runtime_contract import (
    CitationLocator,
    RetrievalContext,
    RuntimeContractError,
    enterprise_mode,
    runtime_contract_status,
)


def _set_enterprise_env(monkeypatch, tmp_path: Path) -> None:
    embedding_path = tmp_path / "bge-large-zh-v1.5"
    rerank_path = tmp_path / "bge-reranker-v2-m3"
    embedding_path.mkdir(exist_ok=True)
    rerank_path.mkdir(exist_ok=True)
    qdrant_ca_path = tmp_path / "qdrant-ca.pem"
    qdrant_ca_path.write_text("test-ca-only", encoding="utf-8")
    values = {
        "APP_ENV": "test",
        "RAG_PROFILE": "enterprise",
        "RAG_ENABLED": "1",
        "RAG_EMBEDDING_PROVIDER": "sentence_transformers",
        "RAG_EMBEDDING_MODEL": "bge-large-zh-v1.5",
        "RAG_EMBEDDING_MODEL_NAME": "bge-large-zh-v1.5",
        "RAG_EMBEDDING_MODEL_PATH": str(embedding_path),
        "RAG_EMBEDDING_DIM": "1024",
        "RAG_EMBEDDING_EXPECTED_DIM": "1024",
        "RAG_EMBEDDING_VERSION": "bge-large-zh-v1.5-v1",
        "RAG_EMBEDDING_EXPECTED_VERSION": "bge-large-zh-v1.5-v1",
        "RAG_EMBEDDING_ALLOW_FALLBACK": "0",
        "RAG_EMBEDDING_FALLBACK_PROVIDER": "disabled",
        "RAG_RERANK_ENABLED": "1",
        "RAG_RERANK_PROVIDER": "bge",
        "RAG_RERANK_MODEL": "bge-reranker-v2-m3",
        "RAG_RERANK_MODEL_NAME": "bge-reranker-v2-m3",
        "RAG_RERANK_MODEL_PATH": str(rerank_path),
        "RAG_RERANK_VERSION": "bge-reranker-v2-m3-v1",
        "RAG_RERANK_EXPECTED_VERSION": "bge-reranker-v2-m3-v1",
        "RAG_RERANK_FALLBACK_PROVIDER": "disabled",
        "RAG_FILE_FALLBACK_ENABLED": "0",
        "RAG_RELEASE_ID": "RAG-R1",
        "RAG_QDRANT_COLLECTION": "rag_chunks_RAG-R1",
        "RAG_QDRANT_ALIAS": "rag_chunks_current",
        "RAG_QDRANT_URL": "https://qdrant:6333",
        "RAG_PROCESS_ROLE": "api",
        "RAG_QDRANT_ACCESS_MODE": "read_only",
        "RAG_QDRANT_API_KEY": "readonly-test-key-" + "a" * 32,
        "RAG_QDRANT_TLS_ENABLED": "1",
        "RAG_QDRANT_STRICT_MODE": "1",
        "RAG_QDRANT_TLS_CA_PATH": str(qdrant_ca_path),
        "RAG_QDRANT_IMAGE_VERSION": "1.18.2",
        "RAG_QDRANT_IMAGE_DIGEST": "sha256:" + "b" * 64,
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_enterprise_runtime_contract_accepts_only_complete_known_profile(monkeypatch, tmp_path):
    _set_enterprise_env(monkeypatch, tmp_path)

    status = runtime_contract_status()

    assert status.enterprise is True
    assert status.available is True
    assert status.embedding.dimensions == 1024
    assert status.release.release_id == "RAG-R1"
    assert status.qdrant.available is True
    assert "readonly-test-key" not in repr(status)


def test_production_always_activates_enterprise_contract(monkeypatch):
    monkeypatch.delenv("RAG_PROFILE", raising=False)
    monkeypatch.setenv("APP_ENV", "production")

    assert enterprise_mode() is True


@pytest.mark.parametrize(
    ("key", "value", "issue"),
    [
        ("RAG_EMBEDDING_PROVIDER", "unknown", "embedding_provider_invalid"),
        ("RAG_EMBEDDING_DIM", "256", "embedding_dimension_invalid"),
        ("RAG_EMBEDDING_MODEL_NAME", "unknown-model", "embedding_model_invalid"),
        ("RAG_EMBEDDING_ALLOW_FALLBACK", "1", "embedding_fallback_forbidden"),
        ("RAG_EMBEDDING_FALLBACK_PROVIDER", "hash", "embedding_fallback_forbidden"),
        ("RAG_EMBEDDING_VERSION", "", "embedding_version_missing"),
        ("RAG_EMBEDDING_EXPECTED_VERSION", "", "embedding_expected_version_missing"),
        ("RAG_EMBEDDING_EXPECTED_VERSION", "other", "embedding_version_mismatch"),
        ("RAG_RERANK_PROVIDER", "heuristic", "rerank_provider_invalid"),
        ("RAG_RERANK_FALLBACK_PROVIDER", "heuristic", "rerank_fallback_forbidden"),
        ("RAG_RERANK_VERSION", "", "rerank_version_missing"),
        ("RAG_RERANK_EXPECTED_VERSION", "", "rerank_expected_version_missing"),
        ("RAG_RERANK_EXPECTED_VERSION", "other", "rerank_version_mismatch"),
        ("RAG_FILE_FALLBACK_ENABLED", "1", "file_fallback_forbidden"),
        ("RAG_RELEASE_ID", "", "release_id_invalid"),
        ("RAG_QDRANT_ALIAS", "other_alias", "release_alias_invalid"),
        ("RAG_QDRANT_URL", "http://qdrant:6333", "qdrant_https_endpoint_required"),
        ("RAG_QDRANT_ACCESS_MODE", "admin", "qdrant_access_mode_invalid"),
        ("RAG_QDRANT_TLS_ENABLED", "0", "qdrant_tls_required"),
        ("RAG_QDRANT_STRICT_MODE", "0", "qdrant_strict_mode_required"),
        ("RAG_QDRANT_API_KEY", "replace_me", "qdrant_api_key_unavailable"),
        ("RAG_QDRANT_IMAGE_VERSION", "latest", "qdrant_image_version_invalid"),
        ("RAG_QDRANT_IMAGE_DIGEST", "sha256:unset", "qdrant_image_digest_invalid"),
    ],
)
def test_enterprise_runtime_contract_rejects_unknown_or_fallback_configuration(
    monkeypatch,
    tmp_path,
    key,
    value,
    issue,
):
    _set_enterprise_env(monkeypatch, tmp_path)
    monkeypatch.setenv(key, value)

    status = runtime_contract_status()

    assert status.available is False
    assert issue in status.issues
    with pytest.raises(RuntimeContractError):
        status.require_available()


def test_enterprise_embedding_failure_is_unavailable_without_hash_fallback(
    monkeypatch, tmp_path
):
    _set_enterprise_env(monkeypatch, tmp_path)
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "unknown")

    result = embedding_service.embed_text_with_metadata("不会加载任何生产模型")

    assert result["embedding"] == []
    assert result["metadata"]["provider"] == "unavailable"
    assert result["metadata"]["fallback"] is False
    assert "embedding_provider_invalid" in result["metadata"]["error"]


def test_enterprise_rerank_failure_does_not_use_heuristic_fallback(monkeypatch, tmp_path):
    _set_enterprise_env(monkeypatch, tmp_path)

    class BrokenReranker:
        name = "bge"

        def rerank(self, query, candidates):
            raise RuntimeError("fake failure")

    monkeypatch.setattr(rerank_service, "get_reranker", lambda: BrokenReranker())

    items, provider, error = rerank_service.rerank_candidates(
        "问题",
        [{"chunk_id": "chunk-1", "content": "证据", "hybrid_score": 0.9}],
    )

    assert items == []
    assert provider == "unavailable"
    assert error == "RuntimeError"


def test_retrieval_context_and_citation_locator_fail_closed():
    context = RetrievalContext(
        tenant_id="default",
        user_id="user-1",
        roles=("viewer",),
        acl_fingerprint="acl-sha256",
        release_id="RAG-R1",
    )
    context.require_valid()
    CitationLocator(
        version_id="version-1",
        page=1,
        section_path=("第一章",),
        char_start=0,
        char_end=8,
        content_hash="a" * 64,
        bbox=(0.0, 0.0, 10.0, 10.0),
    ).require_valid()

    with pytest.raises(RuntimeContractError):
        RetrievalContext(
            tenant_id="",
            user_id="",
            roles=(),
            acl_fingerprint="",
            release_id="",
        ).require_valid()
    with pytest.raises(RuntimeContractError):
        CitationLocator(
            version_id="",
            page=0,
            section_path=(),
            char_start=9,
            char_end=2,
            content_hash="bad",
        ).require_valid()

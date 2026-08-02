import pytest

from scripts.rag_r1_runtime_profile_check import (
    RuntimeProfileCheckError,
    merge_runtime_values,
)


def test_runtime_receives_only_read_key_and_digest():
    qdrant = {
        "QDRANT_ADMIN_API_KEY": "admin-value",
        "QDRANT_READ_ONLY_API_KEY": "reader-value",
        "QDRANT_IMAGE_DIGEST": "sha256:" + "a" * 64,
        "RAG_R1_QDRANT_ROOT": "E:/runtime",
    }
    merged = merge_runtime_values(qdrant, {"RAG_PROFILE": "enterprise"})
    assert merged["RAG_QDRANT_API_KEY"] == "reader-value"
    assert "QDRANT_ADMIN_API_KEY" not in merged
    assert merged["RAG_QDRANT_IMAGE_DIGEST"] == qdrant["QDRANT_IMAGE_DIGEST"]


def test_runtime_merge_rejects_incomplete_qdrant_profile():
    with pytest.raises(RuntimeProfileCheckError, match="incomplete"):
        merge_runtime_values({}, {"RAG_PROFILE": "enterprise"})

from copy import deepcopy

import pytest

from scripts.rag_r1_model_profile import ModelProfileError, render_profile


def _reports():
    versions = {
        "embedding": "sha256:" + "a" * 64,
        "reranker": "sha256:" + "b" * 64,
    }
    admission = {
        "status": "PASS",
        "models": {role: {"version": version} for role, version in versions.items()},
    }
    smoke = {
        "status": "PASS",
        "models": {
            role: {
                "status": "PASS",
                "version": version,
                "fallback_used": False,
                "network_calls": 0,
            }
            for role, version in versions.items()
        },
    }
    return admission, smoke


def test_profile_freezes_versions_paths_dimensions_and_fallbacks():
    content, versions = render_profile(*_reports())
    assert f"RAG_EMBEDDING_VERSION={versions['embedding']}" in content
    assert f"RAG_RERANK_VERSION={versions['reranker']}" in content
    assert "RAG_EMBEDDING_DIM=1024" in content
    assert "RAG_EMBEDDING_ALLOW_FALLBACK=0" in content
    assert "RAG_RERANK_FALLBACK_PROVIDER=disabled" in content
    assert "RAG_FILE_FALLBACK_ENABLED=0" in content
    assert "RAG_QDRANT_ACCESS_MODE=read_only" in content


def test_profile_rejects_runtime_version_or_fallback_drift():
    admission, smoke = _reports()
    drifted = deepcopy(smoke)
    drifted["models"]["embedding"]["version"] = "sha256:" + "c" * 64
    with pytest.raises(ModelProfileError, match="runtime_mismatch"):
        render_profile(admission, drifted)
    fallback = deepcopy(smoke)
    fallback["models"]["reranker"]["fallback_used"] = True
    with pytest.raises(ModelProfileError, match="runtime_unsafe"):
        render_profile(admission, fallback)

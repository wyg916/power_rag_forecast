from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.services import rag_runtime_warmup as warmup


def test_rag_runtime_warmup_is_not_implicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAG_PREWARM_ON_STARTUP", raising=False)
    monkeypatch.setattr(warmup, "enterprise_mode", lambda: (_ for _ in ()).throw(AssertionError))
    assert warmup.prewarm_enterprise_rag_runtime()["status"] == "not_requested"


def test_rag_runtime_warmup_validates_fixed_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_PREWARM_ON_STARTUP", "1")
    monkeypatch.setattr(warmup, "enterprise_mode", lambda: True)
    contract = SimpleNamespace(
        embedding=SimpleNamespace(
            dimensions=1024,
            provider="sentence_transformers",
            model="BAAI/bge-large-zh-v1.5",
            version="sha256:fixed",
        ),
        require_available=lambda: None,
    )
    monkeypatch.setattr(warmup, "runtime_contract_status", lambda: contract)
    monkeypatch.setattr(warmup, "embed_text_with_metadata", lambda _text: {
        "embedding": [0.0] * 1024,
        "metadata": {
            "provider": "sentence_transformers",
            "model": "BAAI/bge-large-zh-v1.5",
            "version": "sha256:fixed",
            "fallback": False,
        },
    })
    monkeypatch.setattr(warmup, "prewarm_reranker", lambda: SimpleNamespace(name="bge"))
    assert warmup.prewarm_enterprise_rag_runtime()["status"] == "ready"


def test_rag_runtime_warmup_fails_closed_on_embedding_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_PREWARM_ON_STARTUP", "1")
    monkeypatch.setattr(warmup, "enterprise_mode", lambda: True)
    contract = SimpleNamespace(
        embedding=SimpleNamespace(
            dimensions=1024,
            provider="sentence_transformers",
            model="BAAI/bge-large-zh-v1.5",
            version="sha256:fixed",
        ),
        require_available=lambda: None,
    )
    monkeypatch.setattr(warmup, "runtime_contract_status", lambda: contract)
    monkeypatch.setattr(warmup, "embed_text_with_metadata", lambda _text: {
        "embedding": [0.0] * 256,
        "metadata": {"provider": "local_hash", "fallback": True},
    })
    with pytest.raises(RuntimeError, match="contract mismatch"):
        warmup.prewarm_enterprise_rag_runtime()

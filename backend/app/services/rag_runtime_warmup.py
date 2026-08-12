from __future__ import annotations

import os
import time
from typing import Any

from .embedding_service import embed_text_with_metadata
from .rag_runtime_contract import enterprise_mode, runtime_contract_status
from .rerank_service import prewarm_reranker


_STATE: dict[str, Any] = {
    "required": False,
    "status": "not_requested",
    "embedding_ms": 0.0,
    "reranker_ms": 0.0,
}


def _enabled() -> bool:
    return os.environ.get("RAG_PREWARM_ON_STARTUP", "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def runtime_warmup_status() -> dict[str, Any]:
    return dict(_STATE)


def prewarm_enterprise_rag_runtime() -> dict[str, Any]:
    required = _enabled()
    _STATE.update(required=required, status="not_requested")
    if not required:
        return runtime_warmup_status()
    if not enterprise_mode():
        raise RuntimeError("RAG prewarm requires the enterprise runtime profile")

    contract = runtime_contract_status()
    contract.require_available()
    started = time.perf_counter()
    embedding = embed_text_with_metadata("电力市场历史同期对比与政策知识检索")
    embedding_ms = round((time.perf_counter() - started) * 1000, 3)
    vector = list(embedding.get("embedding") or [])
    metadata = embedding.get("metadata") or {}
    if (
        len(vector) != contract.embedding.dimensions
        or metadata.get("provider") != contract.embedding.provider
        or metadata.get("model") != contract.embedding.model
        or metadata.get("version") != contract.embedding.version
        or metadata.get("fallback")
    ):
        raise RuntimeError("RAG embedding prewarm contract mismatch")

    started = time.perf_counter()
    reranker = prewarm_reranker()
    reranker_ms = round((time.perf_counter() - started) * 1000, 3)
    if getattr(reranker, "name", "") != "bge":
        raise RuntimeError("RAG reranker prewarm contract mismatch")
    _STATE.update(
        status="ready",
        embedding_ms=embedding_ms,
        reranker_ms=reranker_ms,
        embedding_dim=len(vector),
        embedding_provider=metadata.get("provider"),
        reranker=getattr(reranker, "name", ""),
    )
    return runtime_warmup_status()

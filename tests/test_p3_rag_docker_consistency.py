from __future__ import annotations

from pathlib import Path

from backend.app.services import rag_health_service, rag_service
from backend.app.workers import tasks


def _set_bge_env(monkeypatch, embedding_path: Path, rerank_path: Path) -> None:
    monkeypatch.setenv("RAG_ENABLED", "1")
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "sentence_transformers")
    monkeypatch.setenv("RAG_EMBEDDING_MODEL", "bge-large-zh-v1.5")
    monkeypatch.setenv("RAG_EMBEDDING_MODEL_NAME", "bge-large-zh-v1.5")
    monkeypatch.setenv("RAG_EMBEDDING_MODEL_PATH", str(embedding_path))
    monkeypatch.setenv("RAG_EMBEDDING_DIM", "1024")
    monkeypatch.setenv("RAG_RERANK_ENABLED", "1")
    monkeypatch.setenv("RAG_RERANK_PROVIDER", "bge")
    monkeypatch.setenv("RAG_RERANK_MODEL", "bge-reranker-v2-m3")
    monkeypatch.setenv("RAG_RERANK_MODEL_NAME", "bge-reranker-v2-m3")
    monkeypatch.setenv("RAG_RERANK_MODEL_PATH", str(rerank_path))


def test_rag_health_reports_mounted_bge_paths_without_loading_models(monkeypatch, tmp_path):
    embedding_path = tmp_path / "bge-large-zh-v1.5"
    rerank_path = tmp_path / "bge-reranker-v2-m3"
    embedding_path.mkdir()
    rerank_path.mkdir()
    _set_bge_env(monkeypatch, embedding_path, rerank_path)
    monkeypatch.setattr(rag_health_service, "postgres_engine", lambda: None)

    result = rag_health_service.rag_health()

    assert result["embedding_provider"] == "sentence_transformers"
    assert result["embedding_model_path"] == str(embedding_path)
    assert result["embedding_model_path_exists"] is True
    assert result["embedding_dim"] == 1024
    assert result["rerank_provider"] == "bge"
    assert result["rerank_model_path_exists"] is True
    assert result["fallback_enabled"] is False
    assert result["kb_document_count"] == 0
    assert result["kb_chunk_count"] == 0
    assert result["embedded_chunk_count"] == 0


def test_rag_health_flags_missing_bge_mount_as_fallback(monkeypatch, tmp_path):
    embedding_path = tmp_path / "missing-bge-large-zh-v1.5"
    rerank_path = tmp_path / "missing-bge-reranker-v2-m3"
    _set_bge_env(monkeypatch, embedding_path, rerank_path)
    monkeypatch.setattr(rag_health_service, "postgres_engine", lambda: None)

    result = rag_health_service.rag_health()

    assert result["status"] == "fallback"
    assert result["fallback_enabled"] is True
    assert "embedding_model_path_missing" in result["fallback_reasons"]
    assert "rerank_model_path_missing" in result["fallback_reasons"]


def test_embedding_refresh_handler_returns_warning_when_rag_fallback_enabled(monkeypatch):
    health = {
        "fallback_enabled": True,
        "fallback_reasons": ["embedding_model_path_missing"],
        "embedding_provider": "sentence_transformers",
    }
    monkeypatch.setattr(tasks, "rag_health", lambda: health)
    monkeypatch.setattr(tasks, "backfill_missing_embeddings", lambda: {"available": True, "updated_chunks": 0})
    monkeypatch.setattr(tasks, "refresh_stale_embeddings", lambda: {"available": True, "updated_chunks": 0})

    result = tasks._embedding_refresh_handler({})

    assert result["warnings"]
    assert "embedding_model_path_missing" in result["warnings"][0]
    assert result["rag_health_before"]["fallback_enabled"] is True
    assert result["rag_health_after"]["fallback_enabled"] is True


def test_rag_import_failure_summary_distinguishes_file_failure_classes():
    failed = [
        {"path": "a.md", "reason": rag_service._classify_failure(Path("a.md"), "parse failed")},
        {"path": "b.txt", "reason": rag_service._classify_failure(Path("b.txt"), "UnicodeDecodeError")},
        {"path": "scan.pdf", "reason": rag_service._classify_failure(Path("scan.pdf"))},
        {"path": "table.xlsx", "reason": rag_service._classify_failure(Path("table.xlsx"))},
    ]

    assert failed[0]["reason"] == "parse_failed"
    assert failed[1]["reason"] == "encoding_exception"
    assert failed[2]["reason"] == "scanned_pdf_needs_ocr"
    assert failed[3]["reason"] == "unsupported_format"
    assert rag_service._failure_summary(failed) == {
        "parse_failed": 1,
        "encoding_exception": 1,
        "scanned_pdf_needs_ocr": 1,
        "unsupported_format": 1,
    }

from pathlib import Path

import pytest
import yaml

from scripts.rag_r1_qdrant_preflight import (
    PROJECT_ROOT,
    QdrantPreflightError,
    _runtime_root,
    inspect_preflight,
)


OVERLAY = PROJECT_ROOT / "deploy" / "rag-r1" / "docker-compose.qdrant.yml"


def _values(root: Path) -> dict[str, str]:
    return {
        "RAG_R1_QDRANT_ROOT": str(root),
        "QDRANT_PORT": "6333",
        "QDRANT_ADMIN_API_KEY": "admin-" + "a" * 40,
        "QDRANT_READ_ONLY_API_KEY": "reader-" + "b" * 40,
        "QDRANT_IMAGE_DIGEST": "sha256:" + "c" * 64,
        "RAG_QDRANT_IMAGE_VERSION": "1.18.2",
    }


def test_overlay_is_inert_pinned_local_and_e_drive_persistent():
    compose = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
    services = compose["services"]
    qdrant = services["qdrant"]
    assert qdrant["profiles"] == ["rag-r1"]
    assert qdrant["image"].startswith("qdrant/qdrant:v1.18.2@")
    assert qdrant["ports"] == ["127.0.0.1:${QDRANT_PORT:-6333}:6333"]
    assert qdrant["environment"]["QDRANT__SERVICE__ENABLE_TLS"] == "true"
    assert qdrant["environment"]["QDRANT__STORAGE__STRICT_MODE_CONFIG__ENABLED"] == "true"
    assert all("RAG_R1_QDRANT_ROOT" in volume for volume in qdrant["volumes"])
    assert all("6334" not in port for port in qdrant["ports"])


def test_reader_roles_never_receive_admin_key_and_no_unimplemented_publisher_is_exposed():
    services = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))["services"]
    for name in ("backend", "celery_worker"):
        service = services[name]
        assert service["environment"]["RAG_QDRANT_ACCESS_MODE"] == "read_only"
        assert "QDRANT_ADMIN_API_KEY" not in str(service)
    assert "rag_publisher" not in services


def test_example_is_non_runnable_and_default_rag_activation_is_off():
    example = (PROJECT_ROOT / "deploy" / "rag-r1" / "qdrant.env.example").read_text(
        encoding="utf-8"
    )
    for key in (
        "QDRANT_IMAGE_DIGEST",
        "QDRANT_ADMIN_API_KEY",
        "QDRANT_READ_ONLY_API_KEY",
        "RAG_EMBEDDING_VERSION",
        "RAG_RERANK_VERSION",
    ):
        assert f"\n{key}=\n" in "\n" + example
    assert "RAG_ENABLED=0" in example


def test_preflight_reports_safe_metadata_without_secret_values(monkeypatch, tmp_path: Path):
    root = Path("E:/rag-r1-unit")
    monkeypatch.setattr("scripts.rag_r1_qdrant_preflight.shutil.which", lambda _: None)
    result = inspect_preflight(_values(root), require_assets=False, require_runtime=False)
    assert result["available"] is True
    assert result["runtime_root_drive"] == "E:"
    assert result["bind"] == "127.0.0.1:6333"
    assert result["secret_values_emitted"] is False
    assert "aaaa" not in repr(result) and "bbbb" not in repr(result)


def test_runtime_root_must_be_e_drive_and_outside_repository():
    with pytest.raises(QdrantPreflightError, match="must_be_e_drive"):
        _runtime_root({"RAG_R1_QDRANT_ROOT": "C:/rag-r1"})
    with pytest.raises(QdrantPreflightError, match="outside_repository"):
        _runtime_root({"RAG_R1_QDRANT_ROOT": str(PROJECT_ROOT / ".runtime" / "rag-r1")})

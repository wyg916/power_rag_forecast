from pathlib import Path

import pytest

from scripts.rag_r1_qdrant_bootstrap import (
    PROJECT_ROOT,
    QdrantBootstrapError,
    validate_digest,
    validate_root,
)


def test_digest_gate_accepts_only_sha256():
    digest = "sha256:" + "a" * 64
    assert validate_digest(digest) == digest
    for invalid in ("", "latest", "sha256:unset", "sha256:" + "g" * 64):
        with pytest.raises(QdrantBootstrapError, match="digest_invalid"):
            validate_digest(invalid)


def test_root_gate_requires_new_e_drive_path_outside_repository():
    assert validate_root(Path("E:/rag-r1-bootstrap-unit")) == Path(
        "E:/rag-r1-bootstrap-unit"
    ).resolve()
    with pytest.raises(QdrantBootstrapError, match="must_be_e_drive"):
        validate_root(Path("C:/rag-r1-bootstrap-unit"))
    with pytest.raises(QdrantBootstrapError, match="outside_repository"):
        validate_root(PROJECT_ROOT / ".runtime" / "rag-r1")


def test_existing_root_is_never_overwritten(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda _path: True)
    with pytest.raises(QdrantBootstrapError, match="already_exists"):
        validate_root(Path("E:/rag-r1-existing-unit"))

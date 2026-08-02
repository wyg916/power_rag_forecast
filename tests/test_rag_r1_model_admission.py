from pathlib import Path

import pytest

from scripts.rag_r1_model_admission import (
    MODEL_SPECS,
    ModelAdmissionError,
    _manifest,
    _validate_root,
)


def test_model_specs_freeze_enterprise_profiles():
    embedding = MODEL_SPECS["embedding"]
    reranker = MODEL_SPECS["reranker"]
    assert embedding["model"] == "BAAI/bge-large-zh-v1.5"
    assert embedding["hidden_size"] == 1024
    assert embedding["max_length"] == 512
    assert embedding["license"] == "mit"
    assert reranker["model"] == "BAAI/bge-reranker-v2-m3"
    assert reranker["hidden_size"] == 1024
    assert reranker["max_length"] == 8192
    assert reranker["license"] == "apache-2.0"


def test_manifest_is_deterministic_and_rejects_zero_or_lfs_pointer(tmp_path: Path):
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    first, first_hash = _manifest(tmp_path)
    second, second_hash = _manifest(tmp_path)
    assert first == second and first_hash == second_hash
    assert [item["path"] for item in first] == ["a.txt", "b.txt"]
    (tmp_path / "empty").write_bytes(b"")
    with pytest.raises(ModelAdmissionError, match="zero_byte"):
        _manifest(tmp_path)
    (tmp_path / "empty").write_text(
        "version https://git-lfs.github.com/spec/v1\n", encoding="utf-8"
    )
    with pytest.raises(ModelAdmissionError, match="lfs_pointer"):
        _manifest(tmp_path)


def test_model_root_is_fixed_to_expected_e_drive_location(tmp_path: Path):
    with pytest.raises(ModelAdmissionError, match="model_root_rejected"):
        _validate_root(tmp_path, MODEL_SPECS["embedding"])

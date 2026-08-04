from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import rag_r1_candidate_acceptance as acceptance

def test_registered_development_assets_and_loader_contract():
    corpus_path = acceptance.EXPECTED_RELEASE_ROOT / "candidate_corpus.json"
    acceptance._validate_r3_assets(questions_path=acceptance.EXPECTED_R3_DEVELOPMENT_PATH, corpus_path=corpus_path)
    items = acceptance._load_gold(acceptance.EXPECTED_R3_DEVELOPMENT_PATH, acceptance._read_json(corpus_path), runtime_profile=acceptance.R3_DEVELOPMENT_PROFILE)
    assert len(items) == 40 and sum(bool(item["critical"]) for item in items) == 12


@pytest.mark.parametrize("filename", sorted(acceptance.FORBIDDEN_TUNING_FILENAMES))
def test_r3_asset_validator_rejects_hidden_or_full_set_before_read(tmp_path: Path, filename: str):
    with pytest.raises(acceptance.CandidateAcceptanceError, match="r3_forbidden_tuning_asset"):
        acceptance._validate_r3_assets(questions_path=tmp_path / filename, corpus_path=tmp_path / "candidate_corpus.json")

def _stage_latency() -> dict:
    names = ("auth_acl", "query_embedding", "sparse", "dense", "qdrant", "rrf", "duplicate_merge", "parent_expansion", "content_security", "reranker", "citation_hash", "serialization", "cache")
    return {name: {"sample_count": 40, **{key: 0.0 for key in ("p50_ms", "p90_ms", "p95_ms", "p99_ms", "max_ms")}} for name in names}



def test_r3_gate_requires_acl_coverage_injection_and_zero_errors():
    metrics = {
        "question_count": 40,
        "recall_at_3": 0.90,
        "recall_at_5": 1.0,
        "mrr": 0.85,
        "critical_recall_at_5": 1.0,
        "citation_integrity": 1.0,
        "latency_p95_ms": 1500.0,
        "golden_expected_chunk_full_coverage": 1.0,
        "golden_expected_locator_full_coverage": 1.0,
        "stage_latency_ms": _stage_latency(),
    }
    state = {"points_count": acceptance.EXPECTED_CHUNKS}
    runtime = {
        "runtime_profile": acceptance.R3_DEVELOPMENT_PROFILE,
        "golden_expected_chunk_contract_status": "EVALUATED_WITHIN_TOP5",
        "access_mode": "read_only",
        "write_count": 0,
        "paths_used": [path for _, path in acceptance.READ_ONLY_REQUESTS],
        "acl_negative_denied": True,
        "acl_negative_probe_count": 40,
        "tenant_leakage_count": 0,
        "injection_block_rate": 1.0,
        "injection_probe_count": 3,
        "pipeline_error_count": 0,
        "secret_value_scan_match_count": 0,
        "environment_allowlist_enforced": True, "admin_key_loaded_into_runtime": False,
        "stage_coverage": {
            "postgres_metadata": "CONTROLLER_READ_ONLY_METADATA_PENDING",
        },
        "alias_before": None,
        "alias_after": None,
        "collection_state_before": state,
        "collection_state_after": state,
    }

    assert acceptance._gate(metrics, runtime, expected_count=40)["status"] == "PASS"
    runtime["acl_negative_probe_count"] = 39
    assert acceptance._gate(metrics, runtime, expected_count=40)["status"] == "FAIL"
    runtime["acl_negative_probe_count"] = 40
    runtime["injection_probe_count"] = 2
    assert acceptance._gate(metrics, runtime, expected_count=40)["status"] == "FAIL"
    runtime["injection_probe_count"] = 3
    runtime["golden_expected_chunk_contract_status"] = (
        "CONTRACT_CONFLICT_EXPECTED_CHUNKS_EXCEED_TOP5"
    )
    assert acceptance._gate(metrics, runtime, expected_count=40)["status"] == "FAIL"
    runtime["golden_expected_chunk_contract_status"] = "EVALUATED_WITHIN_TOP5"
    metrics["stage_latency_ms"]["reranker"]["p95_ms"] = -1.0
    assert acceptance._gate(metrics, runtime, expected_count=40)["status"] == "FAIL"


def test_r3_relabelled_asset_is_rejected_before_hash(tmp_path: Path, monkeypatch):
    def fail_hash(_path: Path) -> str:
        raise AssertionError("hash_must_not_run")

    monkeypatch.setattr(acceptance, "_sha256", fail_hash)
    with pytest.raises(
        acceptance.CandidateAcceptanceError,
        match="r3_development_path_forbidden",
    ):
        acceptance._validate_r3_assets(
            questions_path=tmp_path / acceptance.R3_DEVELOPMENT_FILENAME,
            corpus_path=tmp_path / "candidate_corpus.json",
        )


def test_r3_qdrant_env_is_rejected_before_parse(tmp_path: Path, monkeypatch):
    def fail_read(_path: Path) -> dict:
        raise AssertionError("env_must_not_be_read")

    monkeypatch.setattr(acceptance, "_read_env", fail_read)
    with pytest.raises(
        acceptance.CandidateAcceptanceError,
        match="r3_qdrant_env_path_forbidden",
    ):
        acceptance._runtime_values(
            tmp_path / "r3-qdrant-readonly.env",
            None,
            runtime_profile=acceptance.R3_DEVELOPMENT_PROFILE,
        )


def test_isolated_environment_restores_on_error(monkeypatch, tmp_path):
    import config_loader
    key = "R3_CONTRACT_TEMP_SECRET"
    monkeypatch.setenv(key, "preexisting-value")
    monkeypatch.setattr(config_loader, "_ENV_LOADED", False)

    @acceptance._isolated_environment
    def mutate_and_fail(*, runtime_profile):
        assert config_loader._ENV_LOADED
        assert key not in os.environ
        os.environ[key] = "temporary-value"
        raise RuntimeError("expected")

    with pytest.raises(RuntimeError, match="expected"):
        mutate_and_fail(runtime_profile=acceptance.R3_DEVELOPMENT_PROFILE)
    assert os.environ[key] == "preexisting-value"
    assert config_loader._ENV_LOADED is False
    output = acceptance.PROJECT_ROOT / "docs/codex/evidence/r3_contract_cache_guard_never_written.json"
    assert acceptance.main(["--qdrant-env", str(acceptance.EXPECTED_R3_QDRANT_ENV), "--corpus", str(acceptance.EXPECTED_RELEASE_ROOT / "candidate_corpus.json"), "--questions", str(acceptance.EXPECTED_R3_DEVELOPMENT_PATH), "--runtime-profile", acceptance.R3_DEVELOPMENT_PROFILE, "--embedding-cache", str(tmp_path / "cache"), "--output", str(output)]) == 1
    assert not output.exists()

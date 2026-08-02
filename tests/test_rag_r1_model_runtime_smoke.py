import json

import pytest

from scripts.rag_r1_model_runtime_smoke import (
    ModelRuntimeSmokeError,
    RESULT_PREFIX,
    _offline_env,
    _parse_child,
)


def test_offline_environment_closes_network_and_gpu_paths():
    environment = _offline_env()
    assert environment["TRANSFORMERS_OFFLINE"] == "1"
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["HF_HUB_DISABLE_TELEMETRY"] == "1"
    assert environment["CUDA_VISIBLE_DEVICES"] == ""


def test_child_result_contract_parses_one_exact_result():
    payload = {"role": "embedding", "status": "PASS", "shape": [3, 1024]}
    result = _parse_child(RESULT_PREFIX + json.dumps(payload), "embedding")
    assert result["shape"] == [3, 1024]
    with pytest.raises(ModelRuntimeSmokeError, match="result_missing"):
        _parse_child("ordinary log", "embedding")


def test_child_result_contract_rejects_role_mismatch():
    payload = {"role": "reranker", "status": "PASS"}
    with pytest.raises(ModelRuntimeSmokeError, match="contract_invalid"):
        _parse_child(RESULT_PREFIX + json.dumps(payload), "embedding")

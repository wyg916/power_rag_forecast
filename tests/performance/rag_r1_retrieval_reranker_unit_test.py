from __future__ import annotations

import os, sys, time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from backend.app.services import rerank_service


@pytest.fixture(autouse=True)
def _clear_reranker_cache():
    rerank_service._RERANKER_CACHE.clear()
    yield
    rerank_service._RERANKER_CACHE.clear()


def _configure(monkeypatch: pytest.MonkeyPatch, path: str, version: str) -> None:
    monkeypatch.setattr(rerank_service, "enterprise_mode", lambda: False)
    values = {"RAG_RERANK_ENABLED": "1", "RAG_RERANK_PROVIDER": "bge", "RAG_RERANK_MODEL_NAME": "bge-reranker-v2-m3", "RAG_RERANK_MODEL_PATH": path, "RAG_RERANK_VERSION": version, "RAG_RERANK_BATCH_SIZE": "8", "RAG_RERANK_MAX_LENGTH": "128"}
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def _fake_runtime(monkeypatch: pytest.MonkeyPatch, delay: float = 0.0):
    state = SimpleNamespace(tokenizer_loads=0, model_loads=0, model_eval_calls=0, inference_calls=0, tokenizer_batches=[], tokenizer_kwargs=[], text_lengths=[], max_lengths=[], forward_batches=[])

    class Tensor:
        def __init__(self, size: int): self.size = size

        def to(self, _device: str): return self

    class Logits(list):
        def _self(self, *_args: Any): return self

        view = float = cpu = _self

        def tolist(self): return list(self)

    class Tokenizer:
        @classmethod
        def from_pretrained(cls, *_args: Any, **_kwargs: Any):
            state.tokenizer_loads += 1; return cls()

        def __call__(self, pairs: list[list[str]], **kwargs: Any):
            state.tokenizer_batches.append(len(pairs)); state.text_lengths.extend(len(pair[1]) for pair in pairs)
            state.tokenizer_kwargs.append(dict(kwargs))
            state.max_lengths.append(kwargs["max_length"])
            return {"input_ids": Tensor(len(pairs))}

    class Model:
        @classmethod
        def from_pretrained(cls, *_args: Any, **_kwargs: Any):
            time.sleep(delay); state.model_loads += 1; return cls()

        def to(self, _device: str): return self

        def eval(self): state.model_eval_calls += 1; return self

        def __call__(self, **inputs: Any):
            size = next(iter(inputs.values())).size
            state.forward_batches.append(size); return SimpleNamespace(logits=Logits(range(1, size + 1)))

    @contextmanager
    def inference_mode():
        state.inference_calls += 1; yield

    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(AutoTokenizer=Tokenizer, AutoModelForSequenceClassification=Model))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(inference_mode=inference_mode))
    return state


def _provider(version: str = "") -> rerank_service.BGETransformersReranker:
    return rerank_service.BGETransformersReranker("fake-reranker-model", "bge-reranker-v2-m3", batch_size=8, max_length=128, model_version=version)


def test_cache_identity_includes_normalized_path_and_version(monkeypatch: pytest.MonkeyPatch):
    state, path, version = _fake_runtime(monkeypatch), str(Path.cwd() / "fake-reranker-model"), "sha256:" + "1" * 64
    _configure(monkeypatch, path, version)
    first = rerank_service.get_reranker(); monkeypatch.setenv("RAG_RERANK_MODEL_PATH", path + os.sep + ".")
    second = rerank_service.get_reranker()
    assert first is second
    candidate = [{"content": "证据", "hybrid_score": 0.8}]
    assert first.rerank("问题", candidate)[0]["reranker_version"] == version
    second.rerank("问题", candidate)
    assert (state.tokenizer_loads, state.model_loads, state.forward_batches) == (1, 1, [1, 1])
    monkeypatch.setenv("RAG_RERANK_VERSION", "sha256:" + "2" * 64); third = rerank_service.get_reranker()
    assert third is not first and third.model_version != first.model_version


def test_score_pairs_batches_seventeen_as_eight_eight_one(monkeypatch: pytest.MonkeyPatch):
    state = _fake_runtime(monkeypatch); scores = _provider()._score_pairs("问题", [f"候选{index}" for index in range(17)])
    assert len(scores) == 17 and state.tokenizer_batches == state.forward_batches == [8, 8, 1]
    assert state.max_lengths == [128, 128, 128] and state.inference_calls == 3
    assert state.model_eval_calls == 1
    assert all(item["padding"] is True and item["truncation"] is True for item in state.tokenizer_kwargs)


def test_rerank_scores_exact_duplicate_text_once_without_merging_candidates(monkeypatch: pytest.MonkeyPatch):
    state = _fake_runtime(monkeypatch)
    candidates = [
        {"chunk_id": "lower", "content": "same evidence", "hybrid_score": 0.2},
        {"chunk_id": "higher", "content": "same evidence", "hybrid_score": 0.9},
    ]
    result = _provider().rerank("query", candidates)
    assert state.tokenizer_batches == state.forward_batches == [1]
    assert len(result) == len(candidates)
    assert {item["chunk_id"] for item in result} == {"lower", "higher"}
    assert len({item["rerank_raw_score"] for item in result}) == 1
    assert result[0]["chunk_id"] == "higher"


def test_rerank_maps_mixed_duplicates_and_preserves_candidate_metadata(monkeypatch: pytest.MonkeyPatch):
    state = _fake_runtime(monkeypatch)
    shared = {
        "title": "same title",
        "content": "same evidence",
        "source": "same source",
    }
    candidates = [
        {
            **shared,
            "chunk_id": "a-high",
            "document_id": "doc-a",
            "version_id": "version-a",
            "content_hash": "hash-a",
            "tenant_id": "tenant-a",
            "citation": {"quote": "citation-a"},
            "hybrid_score": 0.9,
        },
        {
            "title": "other title",
            "content": "other evidence",
            "source": "other source",
            "chunk_id": "b",
            "document_id": "doc-b",
            "hybrid_score": 0.1,
        },
        {**shared, "chunk_id": "a-low", "document_id": "doc-c", "hybrid_score": 0.2},
    ]
    result = _provider().rerank("query", candidates)
    by_chunk = {item["chunk_id"]: item for item in result}
    assert state.tokenizer_batches == state.forward_batches == [2]
    assert [item["chunk_id"] for item in result] == ["b", "a-high", "a-low"]
    assert by_chunk["a-high"]["rerank_raw_score"] == by_chunk["a-low"]["rerank_raw_score"] == 1.0
    assert by_chunk["b"]["rerank_raw_score"] == 2.0
    assert by_chunk["a-high"]["rerank_score"] == by_chunk["a-low"]["rerank_score"] == 0.0
    assert by_chunk["b"]["rerank_score"] == 1.0
    assert by_chunk["a-high"]["version_id"] == "version-a"
    assert by_chunk["a-high"]["content_hash"] == "hash-a"
    assert by_chunk["a-high"]["tenant_id"] == "tenant-a"
    assert by_chunk["a-high"]["citation"] == {"quote": "citation-a"}


def test_rerank_score_count_mismatch_fails_closed(monkeypatch: pytest.MonkeyPatch):
    provider = _provider()
    monkeypatch.setattr(provider, "_score_pairs", lambda *_args: [])
    with pytest.raises(RuntimeError, match="reranker_score_count_mismatch"):
        provider.rerank("query", [{"content": "evidence", "hybrid_score": 0.5}])


def test_prewarm_is_idempotent_and_preserves_model(monkeypatch: pytest.MonkeyPatch):
    state, version = _fake_runtime(monkeypatch), "sha256:" + "4" * 64; provider = _provider(version)
    monkeypatch.setattr(rerank_service, "get_reranker", lambda: provider)
    assert rerank_service.prewarm_reranker() is provider is rerank_service.prewarm_reranker()
    assert (state.tokenizer_loads, state.model_loads, state.forward_batches) == (1, 1, [8])
    assert min(state.text_lengths) >= 128
    result = provider.rerank("问题", [{"content": "正式候选", "hybrid_score": 0.9}])
    assert (state.tokenizer_loads, state.model_loads) == (1, 1)
    assert state.forward_batches == [8, 1]
    assert result[0]["reranker_version"] == version


def test_concurrent_load_constructs_runtime_once(monkeypatch: pytest.MonkeyPatch):
    state, provider = _fake_runtime(monkeypatch, delay=0.03), _provider()
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: provider._load_model(), range(8)))
    assert (state.tokenizer_loads, state.model_loads) == (1, 1)
    assert len({id(result[0]) for result in results}) == len({id(result[1]) for result in results}) == 1

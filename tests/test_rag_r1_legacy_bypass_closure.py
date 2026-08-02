import os
import sys
from types import SimpleNamespace

from backend.app.services import embedding_service, rerank_service


def test_enterprise_embedding_loader_is_offline_local_only_and_no_remote_code(
    monkeypatch, tmp_path
):
    captured = {}

    class FakeSentenceTransformer:
        def __init__(self, path, **kwargs):
            captured.update({"path": path, **kwargs})

    monkeypatch.setattr(embedding_service, "enterprise_mode", lambda: True)
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    provider = embedding_service.SentenceTransformersEmbeddingProvider(
        model_path=str(tmp_path), model="bge-large-zh-v1.5"
    )
    provider._load_model()

    assert captured["local_files_only"] is True
    assert captured["trust_remote_code"] is False
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_enterprise_reranker_loader_requires_local_safetensors_and_no_remote_code(
    monkeypatch, tmp_path
):
    captured = {}

    class FakeTokenizer:
        @classmethod
        def from_pretrained(cls, path, **kwargs):
            captured["tokenizer"] = {"path": path, **kwargs}
            return cls()

    class FakeModel:
        @classmethod
        def from_pretrained(cls, path, **kwargs):
            captured["model"] = {"path": path, **kwargs}
            return cls()

        def to(self, _device):
            return self

        def eval(self):
            return self

    monkeypatch.setattr(rerank_service, "enterprise_mode", lambda: True)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoTokenizer=FakeTokenizer,
            AutoModelForSequenceClassification=FakeModel,
        ),
    )
    provider = rerank_service.BGETransformersReranker(
        model_path=str(tmp_path), model="bge-reranker-v2-m3"
    )
    provider._load_model()

    assert captured["tokenizer"]["local_files_only"] is True
    assert captured["tokenizer"]["trust_remote_code"] is False
    assert captured["model"]["local_files_only"] is True
    assert captured["model"]["trust_remote_code"] is False
    assert captured["model"]["use_safetensors"] is True


def test_enterprise_fallback_methods_remain_fail_closed(monkeypatch):
    monkeypatch.setattr(embedding_service, "enterprise_mode", lambda: True)
    try:
        embedding_service._fallback_provider()
    except Exception as exc:
        assert getattr(exc, "issues", ()) == ("embedding_fallback_forbidden",)
    else:  # pragma: no cover
        raise AssertionError("enterprise hash fallback must be unreachable")

    class BrokenReranker:
        name = "bge"

        def rerank(self, _query, _candidates):
            raise RuntimeError("fail closed")

    monkeypatch.setattr(rerank_service, "get_reranker", lambda: BrokenReranker())
    monkeypatch.setattr(rerank_service, "enterprise_mode", lambda: True)
    items, provider, error = rerank_service.rerank_candidates(
        "query", [{"content": "evidence", "hybrid_score": 1.0}]
    )
    assert items == [] and provider == "unavailable" and error == "RuntimeError"

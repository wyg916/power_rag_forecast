from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

from config_loader import load_dotenv
from backend.app.services.rag_runtime_contract import enterprise_mode, runtime_contract_status


def _env(name: str, default: str = "") -> str:
    load_dotenv()
    return os.environ.get(name, default).strip()


def _normalized_model_path(value: str) -> str:
    if not value:
        return ""
    return os.path.normcase(str(Path(value).expanduser().resolve(strict=False)))


def _tokens(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", (text or "").lower())
    items = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", compact)
    expanded: list[str] = []
    for item in items:
        expanded.append(item)
        if re.fullmatch(r"[\u4e00-\u9fa5]{4,}", item):
            expanded.extend(item[index : index + 2] for index in range(0, len(item) - 1))
            expanded.extend(item[index : index + 3] for index in range(0, len(item) - 2))
    return set(expanded)


class RerankProvider(Protocol):
    name: str

    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ...


@dataclass
class LocalHeuristicReranker:
    name: str = "local_heuristic"

    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        q_tokens = _tokens(query)
        if not q_tokens:
            return candidates
        output: list[dict[str, Any]] = []
        for item in candidates:
            text = " ".join(str(item.get(key) or "") for key in ("title", "content", "source"))
            c_tokens = _tokens(text)
            overlap = len(q_tokens & c_tokens) / max(1, len(q_tokens))
            phrase_bonus = 0.18 if query and query in text else 0.0
            title_bonus = 0.12 if any(token in str(item.get("title") or "").lower() for token in q_tokens) else 0.0
            rerank_score = min(1.0, overlap * 0.7 + phrase_bonus + title_bonus)
            enriched = dict(item)
            enriched["rerank_score"] = round(rerank_score, 6)
            enriched["final_score"] = round(float(item.get("hybrid_score") or item.get("final_score") or 0.0) * 0.55 + rerank_score * 0.45, 6)
            output.append(enriched)
        output.sort(key=lambda row: row.get("final_score", 0), reverse=True)
        return output


class DisabledReranker:
    name = "disabled"

    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(item, rerank_score=0.0, final_score=float(item.get("hybrid_score") or 0.0)) for item in candidates]


@dataclass
class BGETransformersReranker:
    model_path: str
    model: str
    device: str = "cpu"
    batch_size: int = 8
    max_length: int = 512
    name: str = "bge"
    model_version: str = ""

    def __post_init__(self) -> None:
        self._tokenizer: Any | None = None
        self._model_obj: Any | None = None
        self._load_lock = Lock()
        self._infer_lock = Lock()
        self._warmup_lock = Lock()
        self._warmed_up = False

    def _load_model(self) -> tuple[Any, Any]:
        if self._tokenizer is not None and self._model_obj is not None:
            return self._tokenizer, self._model_obj
        with self._load_lock:
            if self._tokenizer is not None and self._model_obj is not None:
                return self._tokenizer, self._model_obj
            os.environ.setdefault("USE_TF", "0")
            os.environ.setdefault("USE_FLAX", "0")
            os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
            os.environ.setdefault("TRANSFORMERS_NO_FLAX", "1")
            enterprise = enterprise_mode()
            if enterprise:
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            path = self.model_path or self.model
            if not path:
                raise RuntimeError("RAG_RERANK_MODEL_PATH is empty")
            tokenizer = AutoTokenizer.from_pretrained(
                path,
                local_files_only=enterprise,
                trust_remote_code=False,
            )
            model = AutoModelForSequenceClassification.from_pretrained(
                path,
                local_files_only=enterprise,
                trust_remote_code=False,
                use_safetensors=True if enterprise else None,
            )
            model.to(self.device or "cpu")
            model.eval()
            self._tokenizer = tokenizer
            self._model_obj = model
            return tokenizer, model

    def _score_pairs(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        tokenizer, model = self._load_model()
        import torch

        scores: list[float] = []
        batch_size = max(1, int(self.batch_size or 8))
        for start in range(0, len(texts), batch_size):
            batch_texts = texts[start : start + batch_size]
            pairs = [[query, text] for text in batch_texts]
            inputs = tokenizer(
                pairs,
                padding=True,
                truncation=True,
                max_length=max(128, int(self.max_length or 512)),
                return_tensors="pt",
            )
            inputs = {key: value.to(self.device or "cpu") for key, value in inputs.items()}
            with self._infer_lock:
                with torch.inference_mode():
                    logits = model(**inputs).logits.view(-1).float().cpu().tolist()
            scores.extend(float(item) for item in logits)
        return scores

    def warmup(self) -> None:
        if self._warmed_up:
            return
        with self._warmup_lock:
            if self._warmed_up:
                return
            query = "电力市场知识检索预热查询"
            text = (
                "电力市场运行规则、价格预测、风险控制、知识检索、引用校验与访问权限。"
                * 4
            )
            texts = [f"{text}候选序号{index}" for index in range(8)]
            scores = self._score_pairs(query, texts)
            if len(scores) != len(texts):
                raise RuntimeError("reranker_warmup_score_count_mismatch")
            self._warmed_up = True

    @staticmethod
    def _normalize(raw_scores: list[float]) -> list[float]:
        if not raw_scores:
            return []
        low = min(raw_scores)
        high = max(raw_scores)
        if high > low:
            return [(score - low) / (high - low) for score in raw_scores]
        return [1.0 / (1.0 + pow(2.718281828, -score)) for score in raw_scores]

    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not candidates:
            return []
        texts = []
        for item in candidates:
            title = str(item.get("title") or "")
            content = str(item.get("content") or "")
            source = str(item.get("source") or "")
            texts.append(f"{title}\n{content}\n{source}"[:1800])
        raw_scores = self._score_pairs(query, texts)
        normalized_scores = self._normalize(raw_scores)
        output: list[dict[str, Any]] = []
        for item, raw_score, rerank_score in zip(candidates, raw_scores, normalized_scores):
            hybrid_score = float(item.get("hybrid_score") or item.get("final_score") or 0.0)
            enriched = dict(item)
            enriched["rerank_score"] = round(float(rerank_score), 6)
            enriched["rerank_raw_score"] = round(float(raw_score), 6)
            enriched["reranker_model"] = self.model
            enriched["reranker_version"] = self.model_version
            enriched["final_score"] = round(hybrid_score * 0.35 + float(rerank_score) * 0.65, 6)
            output.append(enriched)
        output.sort(key=lambda row: row.get("final_score", 0), reverse=True)
        return output


_RERANKER_CACHE: dict[tuple[Any, ...], RerankProvider] = {}
_RERANKER_CACHE_LOCK = Lock()


def get_reranker() -> RerankProvider:
    if enterprise_mode():
        runtime_contract_status().require_available()
    enabled = (_env("RAG_RERANK_ENABLED", "1") or "1").lower() not in {"0", "false", "no", "off"}
    if not enabled:
        return DisabledReranker()
    provider = (_env("RAG_RERANK_PROVIDER", "local") or "local").lower()
    if provider in {"local", "heuristic", "bge-reranker-base"}:
        return LocalHeuristicReranker()
    if provider in {"bge", "bge_reranker", "transformers", "local_bge"}:
        model_path = _env("RAG_RERANK_MODEL_PATH", _env("RAG_RERANK_MODEL", ""))
        model_name = _env("RAG_RERANK_MODEL_NAME", "") or (Path(model_path).name if model_path else "bge-reranker")
        model_version = _env("RAG_RERANK_VERSION", "")
        device = _env("RAG_RERANK_DEVICE", "cpu") or "cpu"
        try:
            batch_size = int(_env("RAG_RERANK_BATCH_SIZE", "8") or "8")
        except Exception:
            batch_size = 8
        try:
            max_length = int(_env("RAG_RERANK_MAX_LENGTH", "512") or "512")
        except Exception:
            max_length = 512
        cache_key = (
            "bge",
            _normalized_model_path(model_path),
            model_name,
            model_version,
            device,
            batch_size,
            max_length,
        )
        with _RERANKER_CACHE_LOCK:
            if cache_key not in _RERANKER_CACHE:
                _RERANKER_CACHE[cache_key] = BGETransformersReranker(
                    model_path=model_path,
                    model=model_name,
                    model_version=model_version,
                    device=device,
                    batch_size=batch_size,
                    max_length=max_length,
                )
        return _RERANKER_CACHE[cache_key]
    return LocalHeuristicReranker(name=f"{provider}_compatible")


def prewarm_reranker() -> RerankProvider:
    reranker = get_reranker()
    warmup = getattr(reranker, "warmup", None)
    if callable(warmup):
        warmup()
    return reranker


def rerank_candidates(query: str, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str, str]:
    try:
        reranker = get_reranker()
        return reranker.rerank(query, candidates), reranker.name, ""
    except Exception as exc:
        if enterprise_mode():
            issues = getattr(exc, "issues", ())
            error = ",".join(str(item) for item in issues) or exc.__class__.__name__
            return [], "unavailable", error[:300]
        fallback_provider = (_env("RAG_RERANK_FALLBACK_PROVIDER", "heuristic") or "heuristic").lower()
        if fallback_provider in {"local", "heuristic", "local_heuristic"}:
            fallback = LocalHeuristicReranker(name="local_heuristic_fallback").rerank(query, candidates)
            return fallback, "local_heuristic_fallback", str(exc)[:300]
        fallback = [dict(item, rerank_score=0.0, final_score=float(item.get("hybrid_score") or 0.0)) for item in candidates]
        fallback.sort(key=lambda row: row.get("final_score", 0), reverse=True)
        return fallback, "hybrid_score_fallback", str(exc)[:300]

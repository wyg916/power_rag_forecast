from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

from config_loader import load_dotenv
from backend.app.services.rag_runtime_contract import (
    RuntimeContractError,
    enterprise_mode,
    runtime_contract_status,
)


def _env(name: str, default: str = "") -> str:
    load_dotenv()
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    value = (_env(name, "1" if default else "0") or "").lower()
    return value in {"1", "true", "yes", "on"}


def _expected_dimensions() -> int:
    value = _env("RAG_EMBEDDING_EXPECTED_DIM", "")
    if not value:
        return 0
    try:
        return max(0, int(value))
    except Exception:
        return 0


def _tokenize(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", (text or "").lower())
    tokens = [item for item in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", compact) if item]
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        if re.fullmatch(r"[\u4e00-\u9fa5]{4,}", token):
            expanded.extend(token[index : index + 2] for index in range(0, len(token) - 1))
            expanded.extend(token[index : index + 3] for index in range(0, len(token) - 2))
    return list(dict.fromkeys(expanded))[:220]


class EmbeddingProvider(Protocol):
    name: str
    model: str
    version: str

    def embed(self, text: str) -> list[float]:
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...


@dataclass
class LocalHashEmbeddingProvider:
    model: str
    dimensions: int = 256
    name: str = "local_hash"
    version: str = "hash-v1"

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * max(32, int(self.dimensions or 256))
        tokens = _tokenize(text)
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8", errors="ignore"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % len(vector)
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.0 + min(len(token), 12) / 12.0
            vector[index] += sign * weight
        norm = math.sqrt(sum(item * item for item in vector))
        if norm <= 0:
            return []
        return [round(item / norm, 8) for item in vector]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


@dataclass
class DisabledEmbeddingProvider:
    model: str = "disabled"
    name: str = "disabled"
    version: str = "disabled"

    def embed(self, text: str) -> list[float]:
        return []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]


@dataclass
class SentenceTransformersEmbeddingProvider:
    model_path: str
    model: str
    device: str = "cpu"
    batch_size: int = 16
    name: str = "sentence_transformers"
    version: str = "bge-v1"

    def __post_init__(self) -> None:
        self._model_obj: Any | None = None
        self._dimensions = 0
        self._load_lock = Lock()

    @property
    def dimensions(self) -> int:
        return int(self._dimensions or 0)

    def _load_model(self) -> Any:
        if self._model_obj is not None:
            return self._model_obj
        with self._load_lock:
            if self._model_obj is not None:
                return self._model_obj
            os.environ.setdefault("USE_TF", "0")
            os.environ.setdefault("USE_FLAX", "0")
            os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
            os.environ.setdefault("TRANSFORMERS_NO_FLAX", "1")
            enterprise = enterprise_mode()
            if enterprise:
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
            from sentence_transformers import SentenceTransformer

            path = self.model_path or self.model
            if not path:
                raise RuntimeError("RAG_EMBEDDING_MODEL_PATH is empty")
            self._model_obj = SentenceTransformer(
                path,
                device=self.device or "cpu",
                local_files_only=enterprise,
                trust_remote_code=False,
            )
            return self._model_obj

    def embed(self, text: str) -> list[float]:
        values = self.embed_batch([text])
        return values[0] if values else []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        clean_texts = [text or "" for text in texts]
        if not clean_texts:
            return []
        model = self._load_model()
        encoded = model.encode(
            clean_texts,
            batch_size=max(1, int(self.batch_size or 16)),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        vectors: list[list[float]] = []
        for row in encoded:
            vector = [round(float(item), 8) for item in row.tolist()]
            if vector:
                self._dimensions = len(vector)
            vectors.append(vector)
        return vectors


_PROVIDER_CACHE: dict[tuple[Any, ...], EmbeddingProvider] = {}
_PROVIDER_CACHE_LOCK = Lock()

def get_embedding_provider() -> EmbeddingProvider:
    if enterprise_mode():
        runtime_contract_status().require_available()
    provider = (_env("RAG_EMBEDDING_PROVIDER", "local") or "local").lower()
    model = _env("RAG_EMBEDDING_MODEL", "local-hash-bge-small-zh-v1.5-compatible")
    version = _env("RAG_EMBEDDING_VERSION", "")
    if provider in {"0", "false", "disabled", "none"}:
        return DisabledEmbeddingProvider()
    if provider in {"local", "hash", "local_hash"}:
        dimensions = int(_env("RAG_EMBEDDING_DIM", "256") or "256")
        cache_key = ("local_hash", model, dimensions, version or "hash-v1")
        with _PROVIDER_CACHE_LOCK:
            if cache_key not in _PROVIDER_CACHE:
                _PROVIDER_CACHE[cache_key] = LocalHashEmbeddingProvider(
                    model=model,
                    dimensions=dimensions,
                    version=version or "hash-v1",
                )
        return _PROVIDER_CACHE[cache_key]
    if provider in {"sentence_transformers", "sentence-transformers", "sentence_transformer", "bge"}:
        model_path = _env("RAG_EMBEDDING_MODEL_PATH", model)
        model_name = _env("RAG_EMBEDDING_MODEL_NAME", "") or (Path(model_path).name if model_path else model)
        device = _env("RAG_EMBEDDING_DEVICE", "cpu") or "cpu"
        try:
            batch_size = int(_env("RAG_EMBEDDING_BATCH_SIZE", "16") or "16")
        except Exception:
            batch_size = 16
        cache_key = ("sentence_transformers", model_path, model_name, device, batch_size, version or "bge-v1")
        with _PROVIDER_CACHE_LOCK:
            if cache_key not in _PROVIDER_CACHE:
                _PROVIDER_CACHE[cache_key] = SentenceTransformersEmbeddingProvider(
                    model_path=model_path,
                    model=model_name,
                    device=device,
                    batch_size=batch_size,
                    version=version or "bge-v1",
                )
        return _PROVIDER_CACHE[cache_key]
    # Online embedding providers can be added here without changing RAG callers.
    return LocalHashEmbeddingProvider(model=f"{provider}:{model}")


def _fallback_provider() -> EmbeddingProvider:
    if enterprise_mode():
        raise RuntimeContractError(("embedding_fallback_forbidden",))
    fallback = (_env("RAG_EMBEDDING_FALLBACK_PROVIDER", "hash") or "hash").lower()
    dimensions = int(_env("RAG_EMBEDDING_DIM", "256") or "256")
    model = _env("RAG_EMBEDDING_FALLBACK_MODEL", "local-hash-fallback")
    if fallback in {"0", "false", "disabled", "none"}:
        return DisabledEmbeddingProvider()
    return LocalHashEmbeddingProvider(model=model, dimensions=dimensions, version="hash-v1")


def _provider_metadata(provider: EmbeddingProvider, vector: list[float], *, fallback: bool = False, error: str = "") -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "provider": getattr(provider, "name", ""),
        "model": getattr(provider, "model", ""),
        "dim": len(vector),
        "version": getattr(provider, "version", ""),
        "fallback": fallback,
    }
    if error:
        metadata["error"] = error[:200]
    return metadata


def _unavailable_metadata(exc: Exception) -> dict[str, Any]:
    issues = getattr(exc, "issues", ())
    reason = ",".join(str(item) for item in issues) or exc.__class__.__name__
    return {
        "provider": "unavailable",
        "model": "",
        "dim": 0,
        "version": "",
        "fallback": False,
        "error": reason[:200],
    }


def _validate_vector(provider: EmbeddingProvider, vector: list[float]) -> tuple[list[float], str]:
    if not vector:
        return [], "empty_embedding"
    expected = _expected_dimensions()
    if expected and len(vector) != expected:
        return [], f"embedding_dimension_mismatch:{len(vector)}!={expected}"
    return vector, ""


def embed_text_with_metadata(text: str) -> dict[str, Any]:
    try:
        provider = get_embedding_provider()
    except Exception as exc:
        return {"embedding": [], "metadata": _unavailable_metadata(exc)}
    try:
        vector, error = _validate_vector(provider, provider.embed(text))
        if vector:
            return {"embedding": vector, "metadata": _provider_metadata(provider, vector)}
    except Exception as exc:
        error = exc.__class__.__name__
    if not _env_bool("RAG_EMBEDDING_ALLOW_FALLBACK", False):
        return {"embedding": [], "metadata": _provider_metadata(provider, [], error=error)}
    try:
        fallback = _fallback_provider()
        vector, validation_error = _validate_vector(fallback, fallback.embed(text))
        return {
            "embedding": vector,
            "metadata": _provider_metadata(
                fallback,
                vector,
                fallback=True,
                error=validation_error or error,
            ),
        }
    except Exception as exc:
        return {"embedding": [], "metadata": _provider_metadata(provider, [], error=exc.__class__.__name__)}


def embed_batch_with_metadata(texts: list[str]) -> list[dict[str, Any]]:
    try:
        provider = get_embedding_provider()
    except Exception as exc:
        metadata = _unavailable_metadata(exc)
        return [{"embedding": [], "metadata": dict(metadata)} for _ in texts]
    try:
        vectors = provider.embed_batch(texts)
        results = []
        for vector in vectors:
            valid_vector, validation_error = _validate_vector(provider, vector)
            results.append(
                {
                    "embedding": valid_vector,
                    "metadata": _provider_metadata(provider, valid_vector, error=validation_error),
                }
            )
        if results and all(result["embedding"] for result in results):
            return results
        error = next(
            (
                str(result["metadata"].get("error") or "")
                for result in results
                if result["metadata"].get("error")
            ),
            "empty_embedding",
        )
    except Exception as exc:
        error = exc.__class__.__name__
    if not _env_bool("RAG_EMBEDDING_ALLOW_FALLBACK", False):
        return [
            {"embedding": [], "metadata": _provider_metadata(provider, [], error=error)}
            for _ in texts
        ]
    try:
        fallback = _fallback_provider()
        vectors = fallback.embed_batch(texts)
        return [
            {
                "embedding": valid_vector,
                "metadata": _provider_metadata(
                    fallback,
                    valid_vector,
                    fallback=True,
                    error=validation_error or error,
                ),
            }
            for vector in vectors
            for valid_vector, validation_error in [_validate_vector(fallback, vector)]
        ]
    except Exception as exc:
        return [
            {"embedding": [], "metadata": _provider_metadata(provider, [], error=exc.__class__.__name__)}
            for _ in texts
        ]


def embed_text(text: str) -> list[float]:
    return list(embed_text_with_metadata(text).get("embedding") or [])


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return max(0.0, min(1.0, numerator / (left_norm * right_norm)))

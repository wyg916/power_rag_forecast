from __future__ import annotations

import hashlib
import json
import math
import os
import re
import ssl
import unicodedata
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from backend.app.knowledge_enterprise_contracts import ReleaseContract, ReleaseState
from backend.app.repositories.rag_enterprise_repository import (
    EnterpriseReleaseReadError,
    PostgresReleaseContractReader,
)
from backend.app.services.qdrant_vector_store import QdrantReadOnlyStore
from backend.app.services.rag_runtime_contract import (
    RuntimeContractStatus,
    RetrievalContext,
    runtime_contract_status,
)


SPARSE_PROFILE = "bm25-zh-v1"
TOKEN_RE = re.compile(r"[\u3400-\u9fff]+|[a-z0-9]+(?:[._-][a-z0-9]+)*")


class CurrentReleaseReader(Protocol):
    def current_published_release(self, *, tenant_id: str) -> ReleaseContract | None: ...


class RetrievalControlPlane(Protocol):
    def current_alias(self, alias: str) -> str | None: ...

    def collection_details(self, collection: str) -> Mapping[str, Any]: ...

    def sample_payload(self, alias: str, release_id: str) -> Mapping[str, Any] | None: ...

    def query(self, *, collection: str, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class EnterpriseRetrievalBinding:
    context: RetrievalContext | None
    store: QdrantReadOnlyStore | None
    public_reason: str = ""
    diagnostic_reason: str = ""

    @property
    def available(self) -> bool:
        return self.context is not None and self.store is not None and not self.public_reason


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _tokens(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    output: list[str] = []
    for match in TOKEN_RE.finditer(normalized):
        value = match.group(0)
        if "\u3400" <= value[0] <= "\u9fff":
            output.extend(value)
            output.extend(value[index : index + 2] for index in range(len(value) - 1))
        else:
            output.append(value)
    return tuple(output)


class Bm25QueryEncoder:
    def __init__(self, profile: Mapping[str, Any]) -> None:
        raw = dict(profile)
        stored_hash = str(raw.pop("profile_sha256", ""))
        vocabulary = profile.get("vocabulary")
        idf = profile.get("idf")
        if (
            stored_hash != hashlib.sha256(_canonical_bytes(raw)).hexdigest()
            or profile.get("profile") != SPARSE_PROFILE
            or profile.get("tokenizer") != "nfkc-lower-cjk-unigram-bigram-alnum/v1"
            or not isinstance(vocabulary, list)
            or not isinstance(idf, list)
            or len(vocabulary) != len(idf)
            or len(vocabulary) != len(set(vocabulary))
            or not vocabulary
            or float(profile.get("k1") or 0) != 1.2
            or float(profile.get("b") or 0) != 0.75
            or float(profile.get("average_document_length") or 0) <= 0
            or int(profile.get("chunk_count") or 0) <= 0
        ):
            raise ValueError("bm25_profile_invalid")
        try:
            self._lookup = {str(token): index + 1 for index, token in enumerate(vocabulary)}
            self._idf = {index + 1: float(value) for index, value in enumerate(idf)}
        except (TypeError, ValueError) as exc:
            raise ValueError("bm25_profile_invalid") from exc
        if not all(math.isfinite(value) and value >= 0 for value in self._idf.values()):
            raise ValueError("bm25_profile_invalid")
        self._k1 = 1.2
        self._b = 0.75
        self._average_document_length = float(profile["average_document_length"])

    def encode(self, text: str) -> dict[str, list[float] | list[int]]:
        counts = Counter(token for token in _tokens(text) if token in self._lookup)
        length = sum(counts.values())
        if not counts or length < 1:
            return {"indices": [], "values": []}
        scale = self._k1 * (
            1.0 - self._b + self._b * length / self._average_document_length
        )
        weighted: list[tuple[int, float]] = []
        for token, frequency in counts.items():
            index = self._lookup[token]
            value = self._idf[index] * (
                frequency * (self._k1 + 1.0) / (frequency + scale)
            )
            weighted.append((index, round(value, 8)))
        weighted.sort()
        return {
            "indices": [item[0] for item in weighted],
            "values": [item[1] for item in weighted],
        }


@lru_cache(maxsize=2)
def _load_bm25_encoder(path_value: str, mtime_ns: int) -> Bm25QueryEncoder:
    _ = mtime_ns
    try:
        value = json.loads(Path(path_value).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("bm25_profile_unavailable") from exc
    if not isinstance(value, Mapping):
        raise ValueError("bm25_profile_invalid")
    return Bm25QueryEncoder(value)


class QdrantHttpReadOnlyTransport:
    """Qdrant REST adapter restricted to GET and read-only POST operations."""

    def __init__(
        self,
        contract: RuntimeContractStatus,
        env: Mapping[str, str] | None = None,
    ) -> None:
        values = env if env is not None else os.environ
        api_key = str(values.get("RAG_QDRANT_API_KEY", ""))
        ca_path = Path(str(values.get("RAG_QDRANT_TLS_CA_PATH", ""))).resolve()
        bm25_path = Path(str(values.get("RAG_BM25_PROFILE_PATH", ""))).resolve()
        if contract.qdrant.issues or not api_key or not ca_path.is_file():
            raise ValueError("qdrant_runtime_configuration_invalid")
        if not bm25_path.is_file():
            raise ValueError("bm25_profile_unavailable")
        self._endpoint = contract.qdrant.endpoint.rstrip("/")
        self._api_key = api_key
        self._ssl_context = ssl.create_default_context(cafile=str(ca_path))
        self._encoder = _load_bm25_encoder(
            str(bm25_path), bm25_path.stat().st_mtime_ns
        )
        try:
            timeout = float(str(values.get("RAG_QDRANT_TIMEOUT_SECONDS", "10")))
        except ValueError:
            timeout = 10.0
        self._timeout = max(1.0, min(timeout, 30.0))

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        if method not in {"GET", "POST"}:
            raise ValueError("qdrant_read_only_method_required")
        headers = {"accept": "application/json", "api-key": self._api_key}
        data = None
        if payload is not None:
            headers["content-type"] = "application/json"
            data = _canonical_bytes(payload)
        request = Request(
            self._endpoint + path, data=data, headers=headers, method=method
        )
        try:
            with urlopen(
                request, context=self._ssl_context, timeout=self._timeout
            ) as response:
                body = response.read().decode("utf-8")
                value = json.loads(body) if body else {}
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("qdrant_read_failed") from exc
        if response.status != 200 or not isinstance(value, Mapping):
            raise RuntimeError("qdrant_read_failed")
        return value

    def current_alias(self, alias: str) -> str | None:
        value = self._request("/aliases")
        for item in value.get("result", {}).get("aliases", []):
            if item.get("alias_name") == alias:
                return str(item.get("collection_name") or "") or None
        return None

    def collection_details(self, collection: str) -> Mapping[str, Any]:
        value = self._request(f"/collections/{quote(collection, safe='')}")
        result = value.get("result")
        if not isinstance(result, Mapping):
            raise RuntimeError("qdrant_collection_invalid")
        return result

    def sample_payload(self, alias: str, release_id: str) -> Mapping[str, Any] | None:
        value = self._request(
            f"/collections/{quote(alias, safe='')}/points/scroll",
            method="POST",
            payload={
                "filter": {
                    "must": [
                        {"key": "tenant_id", "match": {"value": "default"}},
                        {"key": "release_id", "match": {"value": release_id}},
                        {"key": "status", "match": {"value": "published"}},
                    ]
                },
                "limit": 1,
                "with_payload": True,
                "with_vector": False,
            },
        )
        points = value.get("result", {}).get("points", [])
        if not points:
            return None
        payload = points[0].get("payload")
        return payload if isinstance(payload, Mapping) else None

    def query(
        self, *, collection: str, request: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        mode = str(request.get("mode") or "")
        base = {
            "filter": request.get("filter") or {},
            "limit": int(request.get("limit") or 1),
            "with_payload": bool(request.get("with_payload", True)),
            "with_vector": False,
        }
        if mode == "structured":
            value = self._request(
                f"/collections/{quote(collection, safe='')}/points/scroll",
                method="POST",
                payload=base,
            )
        else:
            query_value = request.get("query")
            using = "dense"
            if mode == "sparse":
                if not isinstance(query_value, Mapping):
                    raise ValueError("sparse_query_invalid")
                query_value = self._encoder.encode(str(query_value.get("text") or ""))
                if not query_value["indices"]:
                    return {"points": []}
                using = "bm25"
            elif mode != "dense":
                raise ValueError("qdrant_query_mode_invalid")
            value = self._request(
                f"/collections/{quote(collection, safe='')}/points/query",
                method="POST",
                payload={**base, "query": query_value, "using": using},
            )
        points = value.get("result", {}).get("points", [])
        if not isinstance(points, list):
            raise RuntimeError("qdrant_query_result_invalid")
        return {"points": points}


class EnterpriseRetrievalRuntime:
    def __init__(
        self,
        release_reader: CurrentReleaseReader | None = None,
        contract_provider: Callable[[], RuntimeContractStatus] = runtime_contract_status,
        transport_factory: Callable[[RuntimeContractStatus], RetrievalControlPlane]
        | None = None,
    ) -> None:
        self._release_reader = release_reader or PostgresReleaseContractReader()
        self._contract_provider = contract_provider
        self._transport_factory = transport_factory or QdrantHttpReadOnlyTransport

    @staticmethod
    def _context(
        contract: RuntimeContractStatus,
        *,
        user_id: str,
        roles: tuple[str, ...],
        run_id: str,
        trace_id: str,
    ) -> RetrievalContext:
        normalized_roles = tuple(sorted({str(role).strip() for role in roles if str(role).strip()}))
        acl_basis = {
            "tenant_id": "default",
            "user_id": user_id,
            "roles": normalized_roles,
        }
        return RetrievalContext(
            tenant_id="default",
            user_id=user_id,
            roles=normalized_roles,
            acl_fingerprint=hashlib.sha256(_canonical_bytes(acl_basis)).hexdigest(),
            release_id=contract.release.release_id,
            run_id=run_id,
            trace_id=trace_id,
        )

    @staticmethod
    def _release_matches(
        release: ReleaseContract, contract: RuntimeContractStatus
    ) -> bool:
        profile = release.embedding_profile
        return all(
            (
                release.status is ReleaseState.PUBLISHED,
                release.release_id == contract.release.release_id,
                release.collection == contract.release.collection,
                profile.provider.lower().replace("-", "_")
                == contract.embedding.provider,
                profile.model.lower().replace("\\", "/")
                == contract.embedding.model.lower().replace("\\", "/"),
                profile.version == contract.embedding.version,
                profile.dimension == contract.embedding.dimensions == 1024,
                profile.sparse_profile == SPARSE_PROFILE,
            )
        )

    @staticmethod
    def _collection_matches(details: Mapping[str, Any]) -> bool:
        params = details.get("config", {}).get("params", {})
        dense = params.get("vectors", {}).get("dense", {})
        sparse = params.get("sparse_vectors", {})
        strict = details.get("strict_mode_config") or details.get("config", {}).get(
            "strict_mode_config", {}
        )
        return all(
            (
                dense.get("size") == 1024,
                str(dense.get("distance") or "").lower() == "cosine",
                "bm25" in sparse,
                strict.get("enabled") is True,
            )
        )

    @staticmethod
    def _payload_matches(
        payload: Mapping[str, Any],
        release: ReleaseContract,
        contract: RuntimeContractStatus,
    ) -> bool:
        return all(
            (
                payload.get("tenant_id") == "default",
                payload.get("release_id") == release.release_id,
                payload.get("status") == "published",
                payload.get("embedding_provider") == release.embedding_profile.provider,
                str(payload.get("embedding_model") or "").lower()
                == contract.embedding.model.lower(),
                payload.get("embedding_version") == contract.embedding.version,
                payload.get("embedding_dimension") == 1024,
                payload.get("sparse_profile") == SPARSE_PROFILE,
                bool(str(payload.get("acl_fingerprint") or "").strip()),
            )
        )

    @staticmethod
    def _unavailable(
        context: RetrievalContext | None, public_reason: str, diagnostic_reason: str
    ) -> EnterpriseRetrievalBinding:
        return EnterpriseRetrievalBinding(
            context=context,
            store=None,
            public_reason=public_reason,
            diagnostic_reason=diagnostic_reason,
        )

    def bind(
        self,
        *,
        user_id: str,
        roles: tuple[str, ...],
        run_id: str,
        trace_id: str,
    ) -> EnterpriseRetrievalBinding:
        contract = self._contract_provider()
        if contract.issues:
            return self._unavailable(
                None, "retrieval_runtime_unavailable", contract.issues[0]
            )
        context = self._context(
            contract,
            user_id=user_id,
            roles=roles,
            run_id=run_id,
            trace_id=trace_id,
        )
        if context.issues():
            return self._unavailable(
                context, "retrieval_context_unavailable", context.issues()[0]
            )
        try:
            release = self._release_reader.current_published_release(
                tenant_id="default"
            )
        except EnterpriseReleaseReadError as exc:
            return self._unavailable(context, "release_unavailable", str(exc))
        except Exception:
            return self._unavailable(
                context, "release_unavailable", "release_fact_read_failed"
            )
        if release is None:
            return self._unavailable(
                context, "release_unavailable", "current_published_release_missing"
            )
        if not self._release_matches(release, contract):
            return self._unavailable(
                context, "release_unavailable", "release_runtime_profile_mismatch"
            )
        try:
            transport = self._transport_factory(contract)
            if transport.current_alias(contract.release.alias) != release.collection:
                return self._unavailable(
                    context, "release_unavailable", "qdrant_alias_mismatch"
                )
            if not self._collection_matches(
                transport.collection_details(release.collection)
            ):
                return self._unavailable(
                    context, "release_unavailable", "qdrant_collection_config_mismatch"
                )
            payload = transport.sample_payload(
                contract.release.alias, release.release_id
            )
            if payload is None or not self._payload_matches(payload, release, contract):
                return self._unavailable(
                    context, "release_unavailable", "qdrant_payload_profile_mismatch"
                )
        except Exception:
            return self._unavailable(
                context, "retrieval_runtime_unavailable", "qdrant_read_failed"
            )
        return EnterpriseRetrievalBinding(
            context=context,
            store=QdrantReadOnlyStore(
                transport,
                contract.release,
                contract.embedding,
                SPARSE_PROFILE,
                payload_embedding_provider=release.embedding_profile.provider,
                payload_embedding_model=release.embedding_profile.model,
            ),
        )


def get_enterprise_retrieval_runtime() -> EnterpriseRetrievalRuntime:
    return EnterpriseRetrievalRuntime()

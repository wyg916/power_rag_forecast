from __future__ import annotations

import hashlib
import json
import math
import os
import re
import ssl
import unicodedata
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from sqlalchemy import text

from backend.app.core.security import CurrentUser
from backend.app.repositories.base import postgres_engine
from backend.app.services.qdrant_security_contract import qdrant_security_status
from backend.app.services.qdrant_vector_store import QdrantReadOnlyStore
from backend.app.services.rag_runtime_contract import RetrievalContext, runtime_contract_status


EXPECTED_RELEASE_ROOT = Path("E:/智能运营分析项目/.runtime/rag/releases/RAG-R1").resolve()
TOKEN_RE = re.compile(r"[\u3400-\u9fff]+|[a-z0-9]+(?:[._-][a-z0-9]+)*")
CURRENT_ALIAS = "rag_chunks_current"


class QdrantReadError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _tokens(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    values: list[str] = []
    for match in TOKEN_RE.finditer(normalized):
        token = match.group(0)
        if "\u3400" <= token[0] <= "\u9fff":
            values.extend(token)
            values.extend(token[index : index + 2] for index in range(len(token) - 1))
        else:
            values.append(token)
    return tuple(values)


def _load_bm25(root: Path = EXPECTED_RELEASE_ROOT) -> dict[str, Any]:
    if root.resolve() != EXPECTED_RELEASE_ROOT:
        raise QdrantReadError("release_root_rejected")
    try:
        value = json.loads((root / "bm25_profile.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QdrantReadError("bm25_profile_unavailable") from exc
    base = dict(value)
    stored = str(base.pop("profile_sha256", ""))
    if stored != hashlib.sha256(_canonical(base)).hexdigest() or value.get("chunk_count") != 8339:
        raise QdrantReadError("bm25_profile_invalid")
    return value


def sparse_query(text_value: str, profile: Mapping[str, Any]) -> dict[str, list[Any]]:
    frequencies: dict[str, int] = {}
    for token in _tokens(text_value):
        frequencies[token] = frequencies.get(token, 0) + 1
    vocabulary = profile.get("vocabulary")
    idf = profile.get("idf")
    if not isinstance(idf, list):
        raise QdrantReadError("bm25_profile_invalid")
    if isinstance(vocabulary, list):
        if (
            len(vocabulary) != len(idf)
            or len(set(vocabulary)) != len(vocabulary)
            or any(not isinstance(token, str) or not token for token in vocabulary)
        ):
            raise QdrantReadError("bm25_profile_invalid")
        lookup = {token: index + 1 for index, token in enumerate(vocabulary)}
        k1 = float(profile.get("k1") or 0.0)
        b = float(profile.get("b") or 0.0)
        average_length = float(profile.get("average_document_length") or 0.0)
        if k1 <= 0.0 or not 0.0 <= b <= 1.0 or average_length <= 0.0:
            raise QdrantReadError("bm25_profile_invalid")
        matched = {token: count for token, count in frequencies.items() if token in lookup}
        length = sum(matched.values())
        if not matched or length < 1:
            return {"indices": [], "values": []}
        denominator_scale = k1 * (1.0 - b + b * length / average_length)
        weighted = [
            (
                lookup[token],
                float(idf[lookup[token] - 1])
                * ((frequency * (k1 + 1.0)) / (frequency + denominator_scale)),
            )
            for token, frequency in matched.items()
        ]
    elif isinstance(vocabulary, Mapping):
        weighted = []
        for token, frequency in frequencies.items():
            index = vocabulary.get(token)
            if isinstance(index, int) and 0 <= index < len(idf):
                weighted.append((index, float(idf[index]) * (1.0 + math.log(frequency))))
    else:
        raise QdrantReadError("bm25_profile_invalid")
    weighted.sort(key=lambda item: item[0])
    return {
        "indices": [item[0] for item in weighted],
        "values": [round(item[1], 8) for item in weighted],
    }


class QdrantHttpsReadOnlyTransport:
    def __init__(self) -> None:
        profile = qdrant_security_status()
        if profile.issues or profile.access_mode != "read_only" or profile.process_role not in {"api", "worker"}:
            raise QdrantReadError(profile.issues[0] if profile.issues else "qdrant_reader_role_invalid")
        ca_path = os.environ.get("RAG_QDRANT_TLS_CA_PATH", "").strip()
        api_key = os.environ.get("RAG_QDRANT_API_KEY", "").strip()
        self.endpoint = profile.endpoint.rstrip("/")
        self.context = ssl.create_default_context(cafile=ca_path)
        self.api_key = api_key
        self.bm25 = _load_bm25()

    def _request(self, path: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        request = Request(
            self.endpoint + path,
            data=_canonical(payload),
            headers={"accept": "application/json", "content-type": "application/json", "api-key": self.api_key},
            method="POST",
        )
        try:
            with urlopen(request, context=self.context, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, HTTPError) as exc:
            raise QdrantReadError("qdrant_read_unavailable") from exc
        points = body.get("result", {}).get("points")
        if not isinstance(points, list):
            raise QdrantReadError("qdrant_response_invalid")
        return {"points": points}

    def _current_alias(self) -> str | None:
        request = Request(
            self.endpoint + "/aliases",
            headers={"accept": "application/json", "api-key": self.api_key},
            method="GET",
        )
        try:
            with urlopen(request, context=self.context, timeout=10) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, HTTPError) as exc:
            raise QdrantReadError("qdrant_alias_unavailable") from exc
        aliases = body.get("result", {}).get("aliases")
        if not isinstance(aliases, list):
            raise QdrantReadError("qdrant_alias_response_invalid")
        matches = [
            str(item.get("collection_name") or "")
            for item in aliases
            if isinstance(item, Mapping) and item.get("alias_name") == CURRENT_ALIAS
        ]
        if len(matches) > 1:
            raise QdrantReadError("qdrant_alias_response_invalid")
        return matches[0] if matches else None

    def query(self, *, collection: str, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if collection != "rag_chunks_RAG-R1":
            raise QdrantReadError("collection_rejected")
        if self._current_alias() != collection:
            raise QdrantReadError("published_alias_mismatch")
        mode = str(request.get("mode") or "")
        common = {
            "filter": request.get("filter"),
            "limit": max(1, min(int(request.get("limit") or 20), 100)),
            "with_payload": True,
            "with_vector": False,
        }
        if mode == "dense":
            payload = {**common, "query": request.get("query"), "using": "dense"}
            return self._request(f"/collections/{quote(CURRENT_ALIAS)}/points/query", payload)
        if mode == "sparse":
            source = request.get("query")
            query_text = str(source.get("text") or "") if isinstance(source, Mapping) else ""
            sparse = sparse_query(query_text, self.bm25)
            if not sparse["indices"]:
                return {"points": []}
            payload = {**common, "query": sparse, "using": "bm25"}
            return self._request(f"/collections/{quote(CURRENT_ALIAS)}/points/query", payload)
        if mode == "structured":
            payload = {**common, "limit": common["limit"]}
            return self._request(f"/collections/{quote(CURRENT_ALIAS)}/points/scroll", payload)
        raise QdrantReadError("query_mode_invalid")


def _postgres_release_is_current(release_id: str, collection: str) -> bool:
    engine = postgres_engine()
    if engine is None:
        raise QdrantReadError("published_release_fact_unavailable")
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT release_id, collection_name, status, is_current
                    FROM kb_releases
                    WHERE tenant_id = 'default' AND is_current
                    """
                )
            ).mappings().one_or_none()
    except Exception as exc:
        raise QdrantReadError("published_release_fact_unavailable") from exc
    return bool(
        row
        and row["release_id"] == release_id
        and row["collection_name"] == collection
        and row["status"] == "published"
        and bool(row["is_current"])
    )


def enterprise_runtime_for_user(
    user: CurrentUser,
) -> tuple[RetrievalContext, QdrantReadOnlyStore]:
    contract = runtime_contract_status()
    contract.require_available()
    if not _postgres_release_is_current(
        contract.release.release_id, contract.release.collection
    ):
        raise QdrantReadError("published_release_fact_mismatch")
    roles = (user.role,) if user.role else ()
    acl_value = {
        "tenant_id": "default",
        "user_id": user.user_id,
        "roles": sorted(roles),
        "permissions": sorted(user.permissions),
    }
    context = RetrievalContext(
        tenant_id="default",
        user_id=user.user_id,
        roles=roles,
        acl_fingerprint=hashlib.sha256(_canonical(acl_value)).hexdigest(),
        release_id=contract.release.release_id,
    )
    context.require_valid()
    store = QdrantReadOnlyStore(
        QdrantHttpsReadOnlyTransport(), contract.release, contract.embedding
    )
    return context, store

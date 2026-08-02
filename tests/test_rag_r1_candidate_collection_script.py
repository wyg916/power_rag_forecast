from __future__ import annotations

from typing import Any

from scripts.rag_r1_candidate_collection import (
    EXPECTED_CANDIDATE_FILE_SHA256,
    EMBEDDING_VERSION,
    _point_id,
    _scroll_payloads,
    _verify_candidate_facts,
    sparse_vector,
)


class PagedQdrant:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def request(self, _path: str, **kwargs: Any) -> tuple[int, dict[str, Any]]:
        payload = dict(kwargs["payload"])
        self.requests.append(payload)
        page = 1 if payload.get("offset") is None else 2
        chunk_ids = [f"chunk-{page}-{index}" for index in range(3)]
        return 200, {
            "result": {
                "points": [
                    {
                        "id": _point_id(chunk_id),
                        "payload": {"chunk_id": chunk_id},
                    }
                    for chunk_id in chunk_ids
                ],
                "next_page_offset": "page-2" if page == 1 else None,
            }
        }


def test_candidate_scroll_uses_bounded_pages_and_preserves_full_identity() -> None:
    client = PagedQdrant()

    payloads = _scroll_payloads(client)  # type: ignore[arg-type]

    assert len(payloads) == 6
    assert [request["limit"] for request in client.requests] == [32, 32]
    assert client.requests[1]["offset"] == "page-2"
    assert all(request["with_vector"] is False for request in client.requests)


class VerificationQdrant:
    def __init__(self, payloads: dict[str, dict[str, Any]]) -> None:
        self.payloads = payloads
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def request(self, path: str, **kwargs: Any) -> tuple[int, dict[str, Any]]:
        payload = dict(kwargs["payload"])
        self.requests.append((path, payload))
        if path.endswith("/count"):
            return 200, {"result": {"count": len(self.payloads)}}
        if path.endswith("/facet"):
            return 200, {
                "result": {
                    "hits": [
                        {"value": chunk_id, "count": 1}
                        for chunk_id in self.payloads
                    ]
                }
            }
        by_id = {_point_id(chunk_id): value for chunk_id, value in self.payloads.items()}
        return 200, {
            "result": [
                {"id": point_id, "payload": by_id[point_id]}
                for point_id in payload["ids"]
            ]
        }


def test_candidate_verification_requires_exact_fact_count_and_identity_samples() -> None:
    payloads = {
        f"chunk-{index}": {
            "chunk_id": f"chunk-{index}",
            "tenant_id": "default",
            "release_id": "RAG-R1",
            "status": "published",
            "candidate_file_sha256": EXPECTED_CANDIDATE_FILE_SHA256,
            "embedding_provider": "sentence_transformers",
            "embedding_model": "BAAI/bge-large-zh-v1.5",
            "embedding_version": EMBEDDING_VERSION,
            "embedding_dimension": 1024,
            "sparse_profile": "bm25-zh-v1",
        }
        for index in range(5)
    }
    client = VerificationQdrant(payloads)

    _verify_candidate_facts(client, payloads)  # type: ignore[arg-type]

    assert client.requests[0][0].endswith("/count")
    assert client.requests[0][1]["exact"] is True
    assert client.requests[1][0].endswith("/facet")
    assert client.requests[1][1]["limit"] == len(payloads)
    assert len(client.requests[2][1]["ids"]) == 3


def test_sparse_vector_reuses_precomputed_profile_maps_without_score_drift() -> None:
    profile = {
        "vocabulary": ["电价", "风险"],
        "idf": [1.5, 2.0],
        "k1": 1.2,
        "b": 0.75,
        "average_document_length": 4.0,
    }
    expected = sparse_vector("电价风险电价", profile)

    reused = sparse_vector(
        "电价风险电价",
        profile,
        vocabulary_lookup={"电价": 1, "风险": 2},
        idf_lookup={1: 1.5, 2: 2.0},
    )

    assert reused == expected

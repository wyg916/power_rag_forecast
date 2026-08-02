import hashlib
from pathlib import Path

from scripts.rag_r1_candidate_collection import (
    CandidateCollectionError,
    EMBEDDING_VERSION,
    PAYLOAD_INDEXES,
    _create_payload_indexes,
    _point_id,
    _parent_contents,
    _retrieve_payloads,
    _validate_existing_collection_report,
    build_bm25_profile,
    build_payloads,
    collection_create_payload,
    sparse_vector,
    tokenize_zh,
)


def _chunk(chunk_id: str, parent_id: str, start: int, text: str, token_count: int = 8):
    return {
        "chunk_id": chunk_id,
        "document_id": "doc_1",
        "version_id": "ver_1",
        "parent_chunk_id": parent_id,
        "content": text,
        "content_hash": hashlib.sha256(text.encode()).hexdigest(),
        "token_count": token_count,
        "citation": {
            "version_id": "ver_1",
            "page": 1,
            "section_path": ["规则"],
            "char_start": start,
            "char_end": start + len(text),
            "bbox": None,
            "asset_id": None,
            "quote": text,
            "content_hash": hashlib.sha256(text.encode()).hexdigest(),
        },
    }


def _artifact():
    chunks = [_chunk("chk_2", "par_1", 4, "市场规则"), _chunk("chk_1", "par_1", 0, "电力交易")]
    return {
        "versions": [
            {
                "source_id": "src_1",
                "document_id": "doc_1",
                "version_id": "ver_1",
                "source_sha256": "a" * 64,
                "content_sha256": "a" * 64,
                "transformed": False,
            }
        ],
        "candidate_manifest": {
            "documents": [
                {
                    "document_id": "doc_1",
                    "version_id": "ver_1",
                    "source_id": "src_1",
                    "source_sha256": "a" * 64,
                    "title": "电力市场规则",
                    "domain": "power-market",
                    "status": "ready",
                    "effective_from": "2026-08-02T00:00:00Z",
                    "effective_to": None,
                    "acl": {"visibility": "tenant", "roles": [], "users": []},
                }
            ],
            "chunks": chunks,
        },
    }


def test_chinese_bm25_profile_and_sparse_vector_are_deterministic():
    chunks = [
        {"content": "电力市场交易规则"},
        {"content": "绿电交易与电力结算"},
    ]
    first = build_bm25_profile(chunks)
    second = build_bm25_profile(list(reversed(chunks)))

    assert tokenize_zh("ＡＢＣ 电力市场") == ("abc", "电", "力", "市", "场", "电力", "力市", "市场")
    assert first == second
    vector = sparse_vector("电力交易", first)
    assert vector["indices"] == sorted(set(vector["indices"]))
    assert len(vector["indices"]) == len(vector["values"]) > 0
    assert all(value > 0 for value in vector["values"])


def test_nonempty_symbol_only_chunk_keeps_dense_path_without_fake_sparse_terms():
    profile = build_bm25_profile([{"content": "——"}, {"content": "电力市场"}])

    assert profile["empty_sparse_chunks"] == 1
    assert sparse_vector("——", profile) == {"indices": [], "values": []}


def test_parent_reconstruction_and_payload_preserve_acl_release_and_citation():
    artifact = _artifact()
    parents = _parent_contents(artifact["candidate_manifest"]["chunks"])
    payloads = build_payloads(
        artifact,
        [{"source_id": "src_1", "detected_format": "pdf"}],
        "f" * 64,
    )

    assert parents == {"par_1": "电力交易市场规则"}
    payload = payloads["chk_1"]
    assert payload["parent_content"] == "电力交易市场规则"
    assert payload["tenant_id"] == "default" and payload["release_id"] == "RAG-R1"
    assert payload["status"] == "published" and payload["acl_public"] is True
    assert payload["source_type"] == "pdf"
    assert payload["embedding_version"] == EMBEDDING_VERSION
    assert payload["citation"]["quote"] == "电力交易"
    assert len(payload["acl_fingerprint"]) == 64


def test_collection_schema_uses_named_dense_sparse_strict_mode_and_required_indexes():
    value = collection_create_payload()
    assert value["vectors"]["dense"] == {"size": 1024, "distance": "Cosine"}
    assert value["sparse_vectors"]["bm25"]["index"]["on_disk"] is True
    assert value["strict_mode_config"]["enabled"] is True
    names = {name for name, _ in PAYLOAD_INDEXES}
    assert {
        "tenant_id", "release_id", "status", "acl_roles", "acl_user_ids",
        "valid_from", "valid_to", "embedding_version", "domain", "source_type",
        "document_id", "version_id", "chunk_id", "parent_chunk_id",
    } <= names


def test_qdrant_point_id_is_uuid_stable_and_release_scoped():
    first = _point_id("chk_1")
    assert first == _point_id("chk_1")
    assert first != _point_id("chk_2")
    assert len(first) == 36


def test_candidate_report_uses_rerun_stable_collection_state():
    source = (
        Path(__file__).parents[1]
        / "scripts"
        / "rag_r1_candidate_collection.py"
    ).read_text(encoding="utf-8")

    assert '"collection_state": "ready"' in source
    assert '"collection_disposition": disposition' not in source


def test_retrieve_splits_server_timeout_batch_and_preserves_identity():
    class StubClient:
        def __init__(self, expected):
            self.requests = []
            self.chunk_ids = {_point_id(chunk_id): chunk_id for chunk_id in expected}

        def request(self, path, *, method, payload):
            self.requests.append((path, method, payload))
            if len(self.requests) == 1:
                return 500, {"status": {"error": "retrieve timed out"}}
            return 200, {
                "result": [
                    {"id": point_id, "payload": {"chunk_id": self.chunk_ids[point_id]}}
                    for point_id in payload["ids"]
                ]
            }

    expected = {f"chk_{index}" for index in range(128)}
    client = StubClient(expected)
    result = _retrieve_payloads(client, expected)

    assert set(result) == expected
    assert [len(item[2]["ids"]) for item in client.requests] == [128, 64, 64]
    assert all(item[0].endswith("/points") for item in client.requests)


def test_existing_payload_indexes_are_validated_without_recreating_them():
    class StubClient:
        def __init__(self, schema):
            self.schema = schema
            self.requests = []

        def request(self, path, *, method="GET", payload=None):
            self.requests.append((path, method, payload))
            return 200, {"result": {"payload_schema": self.schema}}

    schema = {name: {"data_type": value} for name, value in PAYLOAD_INDEXES}
    client = StubClient(schema)
    _create_payload_indexes(client)

    assert len(client.requests) == 1
    assert client.requests[0][1] == "GET"

    schema["tenant_id"] = {"data_type": "integer"}
    try:
        _create_payload_indexes(StubClient(schema))
    except CandidateCollectionError as exc:
        assert str(exc) == "qdrant_payload_index_mismatch:tenant_id"
    else:
        raise AssertionError("mismatched existing payload index must fail closed")


def test_existing_immutable_report_accepts_verified_legacy_state_only_when_facts_match():
    expected = {
        "status": "PASS",
        "point_count": 8339,
        "payload_indexes": [name for name, _ in PAYLOAD_INDEXES],
        "collection_state": "ready",
    }
    existing = {
        "status": "PASS",
        "point_count": 8339,
        "payload_indexes": list(reversed(expected["payload_indexes"])),
        "collection_disposition": "existing",
        "collection_mutated": False,
        "verification_protocol": "deterministic-upsert+exact-count+indexed-fact-count+identity-samples/v1",
    }

    _validate_existing_collection_report(existing, expected)
    existing["point_count"] = 8338
    try:
        _validate_existing_collection_report(existing, expected)
    except CandidateCollectionError as exc:
        assert str(exc) == "candidate_collection_report_fact_mismatch:point_count"
    else:
        raise AssertionError("immutable report fact mismatch must fail closed")

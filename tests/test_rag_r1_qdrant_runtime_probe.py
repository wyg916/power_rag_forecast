import re
from pathlib import Path

from scripts import rag_r1_qdrant_runtime_probe as probe
from scripts.rag_r1_qdrant_runtime_probe import PROBE_RE, _probe_name


def test_probe_collection_name_is_unique_and_safe():
    first = _probe_name()
    second = _probe_name()
    assert PROBE_RE.fullmatch(first)
    assert PROBE_RE.fullmatch(second)
    assert re.fullmatch(r"[a-z0-9_]+", first)


def test_probe_pattern_rejects_alias_or_candidate_names():
    assert not PROBE_RE.fullmatch("rag_chunks_current")
    assert not PROBE_RE.fullmatch("rag_chunks_RAG-R1")


def test_health_probe_is_read_only_and_checks_formal_collection(monkeypatch):
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        probe,
        "_read_only_context",
        lambda _path, require_admin: (
            {
                "QDRANT_READ_ONLY_API_KEY": "r" * 32,
                "QDRANT_IMAGE_DIGEST": "sha256:test",
                "RAG_QDRANT_COLLECTION": "rag_chunks_RAG-R1",
            },
            "https://127.0.0.1:6333",
            object(),
        ),
    )

    def fake_request(_endpoint, _context, path, *, key="", method="GET", payload=None):
        calls.append((method, path))
        assert payload is None
        if path == "/":
            return 200, {"version": "1.18.2"}
        if path == "/collections" and not key:
            return 401, {}
        if path == "/collections":
            return 200, {"result": {"collections": [{"name": "rag_chunks_RAG-R1"}]}}
        if path == "/collections/rag_chunks_RAG-R1":
            return 200, {
                "result": {
                    "points_count": 208,
                    "config": {
                        "params": {"vectors": {"size": 1024, "distance": "Cosine"}},
                        "strict_mode_config": {"enabled": True},
                    },
                }
            }
        if path == "/aliases":
            return 200, {
                "result": {
                    "aliases": [
                        {
                            "alias_name": "rag_chunks_current",
                            "collection_name": "rag_chunks_RAG-R1",
                        }
                    ]
                }
            }
        raise AssertionError(path)

    monkeypatch.setattr(probe, "_request", fake_request)
    result = probe.run_health_probe(Path("runtime.env"))

    assert result["status"] == "PASS"
    assert result["mode"] == "health"
    assert result["write_operations"] == 0
    assert result["persistent_candidate_mutations"] == 0
    assert all(method == "GET" for method, _ in calls)

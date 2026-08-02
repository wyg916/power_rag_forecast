import re

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

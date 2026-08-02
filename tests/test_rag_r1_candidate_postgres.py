from __future__ import annotations

import inspect

import pytest

from scripts import rag_r1_candidate_postgres as module


def test_release_item_identity_is_stable() -> None:
    assert module._item_id("src_1") == module._item_id("src_1")
    assert module._item_id("src_1") != module._item_id("src_2")
    assert module._item_id("src_1").startswith("itm_")


def test_datetime_requires_timezone() -> None:
    assert module._dt("2026-08-02T00:00:00Z").tzinfo is not None
    with pytest.raises(module.CandidatePostgresError, match="timezone_required"):
        module._dt("2026-08-02T00:00:00")


def test_candidate_import_is_explicit_and_never_publishes() -> None:
    source = inspect.getsource(module)
    assert "--confirm-local-candidate-write" in source
    assert "'candidate',false" in source
    assert '"is_current": False' in source
    assert '"production_switch": False' in source
    for forbidden in ("TRUNCATE ", "DROP TABLE", "DELETE FROM", "UPDATE kb_releases SET status='published'"):
        assert forbidden not in source


def test_fixed_candidate_identity() -> None:
    assert module.RELEASE_ID == "RAG-R1"
    assert module.TENANT_ID == "default"
    assert module.COLLECTION == "rag_chunks_RAG-R1"
    assert module.ALIAS == "rag_chunks_current"
    assert len(module.EXPECTED_LEDGER_SHA256) == 64
    assert len(module.EXPECTED_CANDIDATE_FILE_SHA256) == 64

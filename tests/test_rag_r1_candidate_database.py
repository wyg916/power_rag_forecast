from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from scripts.rag_r1_candidate_database import (
    CandidateDatabaseError,
    CandidateFacts,
    EXPECTED_TARGET,
    _hash,
    _mismatch_count,
    _release_item,
    load_database_url,
    repair_manifest,
)


def test_canonical_hash_is_order_independent() -> None:
    assert _hash({"b": 2, "a": 1}) == _hash({"a": 1, "b": 2})


def test_release_item_identity_is_deterministic() -> None:
    first = _release_item("src_1", "a" * 64, "isolated", reason="unsupported")
    second = _release_item("src_1", "a" * 64, "isolated", reason="unsupported")
    assert first == second
    assert first["item_id"].startswith("item_")
    assert first["document_id"] is None
    assert first["chunk_count"] == 0


def test_mismatch_count_is_field_scoped() -> None:
    expected = {"a": 1, "b": 2, "ignored": 3}
    actual = {"a": 1, "b": 9, "ignored": 8}
    assert _mismatch_count(expected, actual, ("a", "b")) == 1


def test_database_target_guard_accepts_only_frozen_target(tmp_path: Path) -> None:
    env = tmp_path / "runtime.env"
    env.write_text(
        "DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/postgres\n",
        encoding="utf-8",
    )
    url = load_database_url(env)
    assert {
        "host": url.host,
        "port": url.port,
        "database": url.database,
        "user": url.username,
    } == EXPECTED_TARGET


@pytest.mark.parametrize(
    "url",
    (
        "postgresql+psycopg://postgres@remote:5432/postgres",
        "postgresql+psycopg://postgres@localhost:5433/postgres",
        "postgresql+psycopg://postgres@localhost:5432/other",
        "postgresql+psycopg://other@localhost:5432/postgres",
    ),
)
def test_database_target_guard_rejects_drift(tmp_path: Path, url: str) -> None:
    env = tmp_path / "runtime.env"
    env.write_text(f"DATABASE_URL={url}\n", encoding="utf-8")
    with pytest.raises(CandidateDatabaseError, match="database_target_rejected"):
        load_database_url(env)


class _Cursor:
    rowcount = 1

    def __init__(self) -> None:
        self.sql = ""
        self.params = ()

    def execute(self, sql: str, params: tuple[str, ...]) -> None:
        self.sql = sql
        self.params = params


def _facts() -> CandidateFacts:
    return CandidateFacts(
        corpus={}, envelope={}, ledger=(), admission={}, documents=(), versions=(),
        chunks=(), release_items=(), manifest_sha256="b" * 64,
        artifact_sha256="a" * 64, ledger_sha256="c" * 64,
    )


def test_manifest_repair_is_single_row_compare_and_swap() -> None:
    cursor = _Cursor()
    assert repair_manifest(cursor, _facts()) == 1
    normalized = " ".join(cursor.sql.split())
    assert "UPDATE kb_releases" in normalized
    assert "tenant_id=%s AND release_id=%s" in normalized
    assert "status='candidate' AND is_current=false" in normalized
    assert "manifest_sha256=%s" in normalized
    assert cursor.params == ("b" * 64, "default", "RAG-R1", "a" * 64)


def test_manifest_repair_rejects_impossible_cardinality() -> None:
    cursor = _Cursor()
    cursor.rowcount = 2
    with pytest.raises(CandidateDatabaseError, match="cardinality"):
        repair_manifest(cursor, _facts())


def test_sqlalchemy_url_fixture_is_postgres() -> None:
    assert make_url(
        "postgresql+psycopg://postgres@localhost:5432/postgres"
    ).get_backend_name() == "postgresql"

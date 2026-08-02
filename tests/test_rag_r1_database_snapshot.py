from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from scripts.rag_r1_database_snapshot import EXPECTED, _load_url


def _env(tmp_path: Path, value: str) -> Path:
    path = tmp_path / "database.env"
    path.write_text(f"DATABASE_URL={value}\n", encoding="utf-8")
    return path


def test_snapshot_target_accepts_only_fixed_local_postgres(tmp_path: Path):
    url = _load_url(
        _env(tmp_path, "postgresql+psycopg://postgres:secret@localhost:5432/postgres")
    )
    assert url.host == EXPECTED["host"]
    assert url.port == EXPECTED["port"]
    assert url.database == EXPECTED["database"]
    assert url.username == EXPECTED["user"]


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://postgres:secret@remote:5432/postgres",
        "postgresql+psycopg://other:secret@localhost:5432/postgres",
        "postgresql+psycopg://postgres:secret@localhost:5433/postgres",
        "postgresql+psycopg://postgres:secret@localhost:5432/other",
    ],
)
def test_snapshot_target_rejects_scope_expansion(tmp_path: Path, url: str):
    with pytest.raises(RuntimeError, match="^database_target_rejected"):
        _load_url(_env(tmp_path, url))


def test_snapshot_url_is_parsed_without_exposing_password(tmp_path: Path):
    url = _load_url(
        _env(tmp_path, "postgresql+psycopg://postgres:do-not-print@localhost:5432/postgres")
    )
    assert make_url(url).password == "do-not-print"
    assert "do-not-print" not in repr(EXPECTED)

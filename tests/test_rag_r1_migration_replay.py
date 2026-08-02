from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from scripts.rag_r1_migration_replay import (
    DOWN_REVISION,
    ENTERPRISE_TABLES,
    HEAD_COLUMNS,
    HEAD_REVISION,
    MigrationReplayError,
    SCHEMA_PREFIX,
    _alembic_environment,
    _assert_down,
    _assert_head,
    _load_url,
    _validate_identifier,
)


def _env(tmp_path: Path, url: str) -> Path:
    path = tmp_path / "database.env"
    path.write_text(f"MIGRATION_DATABASE_URL={url}\n", encoding="utf-8")
    return path


def _catalog(revision: str, enterprise: bool) -> dict:
    tables = set(HEAD_COLUMNS)
    if enterprise:
        tables |= ENTERPRISE_TABLES
    return {
        "tables": sorted(tables),
        "columns": {
            table: [{"name": name} for name in sorted(columns if enterprise else set())]
            for table, columns in HEAD_COLUMNS.items()
        },
        "alembic_revision": revision,
    }


def test_fixed_local_database_target(tmp_path: Path):
    url = _load_url(
        _env(tmp_path, "postgresql+psycopg://postgres@localhost:5432/postgres")
    )
    assert url.host == "localhost"
    assert url.database == "postgres"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://postgres@remote:5432/postgres",
        "postgresql+psycopg://other@localhost:5432/postgres",
        "postgresql+psycopg://postgres@localhost:5433/postgres",
        "postgresql+psycopg://postgres@localhost:5432/production",
    ],
)
def test_database_target_scope_expansion_is_rejected(tmp_path: Path, url: str):
    with pytest.raises(MigrationReplayError, match="database_target_rejected"):
        _load_url(_env(tmp_path, url))


def test_isolated_names_are_strictly_prefix_bound():
    schema = f"{SCHEMA_PREFIX}unit"
    role = f"{schema}_role"
    assert _validate_identifier(schema) == schema
    assert _validate_identifier(role, role=True) == role
    for value in ("public", "beta10d_other", f"{SCHEMA_PREFIX}bad-name"):
        with pytest.raises(MigrationReplayError):
            _validate_identifier(value)


def test_alembic_environment_is_schema_and_role_bound():
    schema = f"{SCHEMA_PREFIX}unit"
    role = f"{schema}_role"
    url = make_url("postgresql+psycopg://postgres@localhost:5432/postgres")
    environment = _alembic_environment(url, schema, role)
    assert environment["ALEMBIC_TARGET_SCHEMA"] == schema
    assert environment["ALEMBIC_EXECUTION_ROLE"] == role
    assert environment["ALEMBIC_SCHEMA_PREFIX"] == SCHEMA_PREFIX
    assert environment["MIGRATION_DATABASE_URL"] == ""


def test_head_contract_accepts_complete_catalog_and_rejects_missing_table():
    catalog = _catalog(HEAD_REVISION, enterprise=True)
    _assert_head(catalog)
    catalog["tables"].remove("kb_releases")
    with pytest.raises(MigrationReplayError, match="head_tables_missing"):
        _assert_head(catalog)


def test_down_contract_accepts_clean_rollback_and_rejects_residual_column():
    catalog = _catalog(DOWN_REVISION, enterprise=False)
    _assert_down(catalog)
    catalog["columns"]["kb_documents"] = [{"name": "tenant_id"}]
    with pytest.raises(MigrationReplayError, match="down_columns_remaining"):
        _assert_down(catalog)

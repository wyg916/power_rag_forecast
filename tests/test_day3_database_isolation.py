from __future__ import annotations

import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text

from scripts.day3_test_database_guard import (
    EXPECTED_ALEMBIC_HEAD,
    ISOLATION_FLAG,
    ROLE_ENV,
    SCHEMA_ENV,
    TEST_ROLE_SUFFIX,
    DatabaseIsolationError,
    build_isolated_security_url,
    build_isolated_runtime_url,
    validate_database_target,
    validate_isolated_identifier,
    verify_isolated_runtime,
)


def test_database_target_gate_rejects_nonlocal_or_wrong_identity():
    validate_database_target("postgresql://postgres@localhost:5432/postgres")
    for unsafe in (
        "sqlite:///pytest.db",
        "postgresql://postgres@db.example.com:5432/postgres",
        "postgresql://application@localhost:5432/postgres",
        "postgresql://postgres@localhost:5433/postgres",
        "postgresql://postgres@localhost:5432/production",
    ):
        with pytest.raises(DatabaseIsolationError):
            validate_database_target(unsafe)


def test_schema_and_role_names_are_prefix_bound():
    schema = "beta10d_day3_close_unit"
    role = f"{schema}{TEST_ROLE_SUFFIX}"
    assert validate_isolated_identifier(schema, kind="测试 Schema") == schema
    assert validate_isolated_identifier(role, kind="测试角色") == role
    for unsafe in ("public", "beta10d_test_unit", "beta10d_day3_close_bad-name", 'beta10d_day3_close_x"'):
        with pytest.raises(DatabaseIsolationError):
            validate_isolated_identifier(unsafe, kind="测试对象")


def test_runtime_url_contains_only_isolated_search_path_and_role():
    schema = "beta10d_day3_close_unit"
    role = f"{schema}{TEST_ROLE_SUFFIX}"
    runtime = build_isolated_runtime_url(
        "postgresql://postgres:test-placeholder@localhost:5432/postgres",
        schema,
        role,
    )
    assert "search_path%3D" in runtime
    assert schema in runtime
    assert role in runtime
    assert "public" not in runtime
    security_runtime = build_isolated_security_url(runtime)
    assert security_runtime != runtime
    assert "beta10d_security_isolated" in security_runtime
    assert schema in security_runtime
    assert role in security_runtime
    assert "public" not in security_runtime


def test_plain_pytest_mode_blocks_inherited_local_database_url():
    environment = os.environ.copy()
    environment.pop(ISOLATION_FLAG, None)
    environment.pop(SCHEMA_ENV, None)
    environment.pop(ROLE_ENV, None)
    environment["DATABASE_URL"] = "postgresql://postgres:test-placeholder@localhost:5432/postgres"
    code = """
import os
from scripts.day3_test_database_guard import configure_pytest_database
result = configure_pytest_database()
assert result["mode"] == "disabled-no-database"
assert result["local_database_url_was_blocked"] is True
assert os.environ["DATABASE_URL"] == ""
assert os.environ["SECURITY_DATABASE_URL"] == ""
assert os.environ["MIGRATION_DATABASE_URL"] == ""
assert "default_transaction_read_only=on" in os.environ["PGOPTIONS"]
from backend.app.repositories.base import postgres_engine
assert postgres_engine() is None
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_active_pytest_database_is_restricted_and_not_public():
    if os.environ.get(ISOLATION_FLAG) != "1":
        pytest.skip("requires the Day 3 isolated database runner")
    assert os.environ.get(ISOLATION_FLAG) == "1"
    schema = os.environ[SCHEMA_ENV]
    role = os.environ[ROLE_ENV]
    verification = verify_isolated_runtime(os.environ["DATABASE_URL"], schema, role)
    assert verification["identity"]["current_schema"] == schema
    assert verification["identity"]["current_user"] == role
    assert verification["identity"]["current_schemas"][0] == schema
    assert "public" not in verification["identity"]["current_schemas"]
    assert verification["alembic_head"] == EXPECTED_ALEMBIC_HEAD
    assert not any(verification["public_write_privileges"].values())
    security_verification = verify_isolated_runtime(
        os.environ["SECURITY_DATABASE_URL"], schema, role
    )
    assert security_verification["identity"]["current_schema"] == schema
    assert security_verification["identity"]["current_user"] == role
    assert "public" not in security_verification["identity"]["current_schemas"]
    assert not any(security_verification["public_write_privileges"].values())


def test_restricted_role_cannot_write_public():
    if os.environ.get(ISOLATION_FLAG) != "1":
        pytest.skip("requires the Day 3 isolated database runner")
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True, future=True)
    try:
        with engine.begin() as connection:
            with pytest.raises(Exception):
                connection.execute(
                    text(
                        """
                        INSERT INTO public.audit_logs
                            (actor, action, resource_type, status)
                        VALUES
                            ('day3-isolation-probe', 'blocked', 'test', 'blocked')
                        """
                    )
                )
    finally:
        engine.dispose()

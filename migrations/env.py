from __future__ import annotations

from logging.config import fileConfig
import os
from pathlib import Path
import re
import sys

from alembic import context
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import get_settings  # noqa: E402
from backend.app.db.base import Base  # noqa: E402


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _optional_identifier(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    if not _IDENTIFIER_RE.fullmatch(value):
        raise RuntimeError(f"{name} 不是安全的 PostgreSQL 标识符。")
    return value


def _isolated_schema() -> str | None:
    schema = _optional_identifier("ALEMBIC_TARGET_SCHEMA")
    if schema is None:
        return None
    if schema == "public":
        raise RuntimeError("ALEMBIC_TARGET_SCHEMA 不得为 public。")
    prefix = os.environ.get("ALEMBIC_SCHEMA_PREFIX", "").strip()
    if not prefix or not schema.startswith(prefix):
        raise RuntimeError("ALEMBIC_TARGET_SCHEMA 未通过 ALEMBIC_SCHEMA_PREFIX 前缀门禁。")
    return schema


def _validate_expected_target(url: str) -> None:
    parsed = make_url(url)
    expected = {
        "database": os.environ.get("ALEMBIC_EXPECTED_DATABASE", "").strip(),
        "host": os.environ.get("ALEMBIC_EXPECTED_HOST", "").strip(),
        "port": os.environ.get("ALEMBIC_EXPECTED_PORT", "").strip(),
        "user": os.environ.get("ALEMBIC_EXPECTED_USER", "").strip(),
    }
    actual = {
        "database": parsed.database or "",
        "host": parsed.host or "",
        "port": str(parsed.port or ""),
        "user": parsed.username or "",
    }
    for key, value in expected.items():
        if value and actual[key] != value:
            raise RuntimeError(f"Alembic 目标 {key} 与 ALEMBIC_EXPECTED_{key.upper()} 不一致。")


def _database_url() -> str:
    url = get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL 未配置，无法执行 Alembic migration。")
    _validate_expected_target(url)
    return url


def run_migrations_offline() -> None:
    if _isolated_schema() is not None:
        raise RuntimeError("隔离 Schema 迁移禁止 offline 模式；无法安全设置 search_path。")
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine, text

    connectable = create_engine(_database_url(), pool_pre_ping=True, future=True)
    with connectable.connect() as connection:
        schema = _isolated_schema()
        configure_kwargs: dict[str, object] = {
            "connection": connection,
            "target_metadata": target_metadata,
        }
        if schema is not None:
            role = _optional_identifier("ALEMBIC_EXECUTION_ROLE")
            if role is not None:
                prefix = os.environ.get("ALEMBIC_SCHEMA_PREFIX", "").strip()
                if not role.startswith(prefix):
                    raise RuntimeError("ALEMBIC_EXECUTION_ROLE 未通过 ALEMBIC_SCHEMA_PREFIX 前缀门禁。")
                connection.execute(text(f'SET ROLE "{role}"'))
            connection.execute(text(f'SET search_path TO "{schema}", pg_catalog'))
            current_schema = connection.execute(text("SELECT current_schema()")).scalar_one()
            if current_schema != schema:
                raise RuntimeError("Alembic 隔离 search_path 未生效。")
            # SET ROLE/search_path are session settings. Commit their implicit
            # SQLAlchemy transaction so Alembic owns and commits migration DDL.
            connection.commit()
            configure_kwargs["version_table_schema"] = schema
            configure_kwargs["include_schemas"] = False
        context.configure(**configure_kwargs)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

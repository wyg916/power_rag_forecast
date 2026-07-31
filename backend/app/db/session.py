from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings


def create_app_engine(database_url: str | None = None) -> Engine:
    url = (database_url or get_settings().database_url).strip()
    if not url:
        raise RuntimeError("DATABASE_URL 未配置，无法创建 PostgreSQL SQLAlchemy engine。")
    return create_engine(url, pool_pre_ping=True, future=True, echo=get_settings().database_echo)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_app_engine()


@lru_cache(maxsize=1)
def get_security_engine() -> Engine:
    url = get_settings().security_database_url.strip()
    if not url:
        raise RuntimeError("SECURITY_DATABASE_URL 未配置，禁止回退到普通运行身份。")
    return create_app_engine(url)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def validate_runtime_database_roles(runtime_engine: Engine, security_engine: Engine) -> dict[str, str]:
    if runtime_engine.dialect.name != "postgresql" or security_engine.dialect.name != "postgresql":
        return {"status": "not_postgresql"}

    dangerous_roles = (
        "pg_read_all_data",
        "pg_write_all_data",
        "pg_read_server_files",
        "pg_write_server_files",
        "pg_execute_server_program",
        "pg_signal_backend",
    )

    def inspect_role(engine: Engine) -> dict[str, object]:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT current_user AS role_name,
                           r.rolsuper, r.rolcreatedb, r.rolcreaterole,
                           r.rolreplication, r.rolbypassrls,
                           pg_has_role(current_user, 'pg_read_all_data', 'member') AS pg_read_all_data,
                           pg_has_role(current_user, 'pg_write_all_data', 'member') AS pg_write_all_data,
                           pg_has_role(current_user, 'pg_read_server_files', 'member') AS pg_read_server_files,
                           pg_has_role(current_user, 'pg_write_server_files', 'member') AS pg_write_server_files,
                           pg_has_role(current_user, 'pg_execute_server_program', 'member') AS pg_execute_server_program,
                           pg_has_role(current_user, 'pg_signal_backend', 'member') AS pg_signal_backend,
                           has_database_privilege(current_user, current_database(), 'CREATE') AS database_create,
                           has_schema_privilege(current_user, 'public', 'CREATE') AS schema_create
                    FROM pg_roles r
                    WHERE r.rolname = current_user
                    """
                )
            ).mappings().one()
            return dict(row)

    runtime = inspect_role(runtime_engine)
    security = inspect_role(security_engine)
    for label, values in (("runtime", runtime), ("security", security)):
        forbidden = [
            key
            for key in ("rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication", "rolbypassrls", "database_create", "schema_create")
            if bool(values.get(key))
        ]
        forbidden.extend(role for role in dangerous_roles if bool(values.get(role)))
        if forbidden:
            raise RuntimeError(f"{label} 数据库身份具有禁止权限：{','.join(forbidden)}")
    if runtime["role_name"] == security["role_name"]:
        raise RuntimeError("普通运行身份与安全仓储身份必须分离。")
    with runtime_engine.connect() as conn:
        sensitive = conn.execute(
            text(
                """
                SELECT has_table_privilege(current_user, 'public.users', 'SELECT') AS users_select,
                       has_table_privilege(current_user, 'public.audit_logs', 'SELECT') AS audit_select,
                       has_table_privilege(current_user, 'public.alembic_version', 'SELECT') AS migration_select
                """
            )
        ).mappings().one()
    leaked = [name for name, allowed in sensitive.items() if bool(allowed)]
    if leaked:
        raise RuntimeError(f"普通运行身份可读取禁止对象：{','.join(leaked)}")
    return {
        "status": "validated",
        "runtime_role": str(runtime["role_name"]),
        "security_role": str(security["role_name"]),
    }


def reset_db_cache() -> None:
    get_engine.cache_clear()
    get_security_engine.cache_clear()
    get_sessionmaker.cache_clear()

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
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
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def reset_db_cache() -> None:
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()

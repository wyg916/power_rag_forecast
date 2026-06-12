from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from config_loader import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
logger = logging.getLogger(__name__)


def _env(name: str, default: str = "") -> str:
    load_dotenv()
    return os.environ.get(name, default)


def _bool_env(name: str, default: bool = False) -> bool:
    value = str(_env(name, "1" if default else "0")).strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(str(_env(name, str(default))).strip() or default)
    except Exception:
        return default


@dataclass(frozen=True)
class Settings:
    project_root: Path
    app_env: str
    database_url: str
    database_primary: str
    database_allow_legacy_fallback: bool
    redis_url: str
    task_execution_mode: str
    database_echo: bool
    llm_provider: str
    llm_base_url: str
    llm_model: str
    auth_required: bool
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_access_token_expire_minutes: int
    rag_profile: str
    rag_keyword_limit: int
    rag_vector_limit: int
    rag_rerank_candidate_limit: int
    rag_cache_ttl_seconds: int

    @property
    def has_database_url(self) -> bool:
        return bool(self.database_url.strip())

    @property
    def wants_postgres_primary(self) -> bool:
        return self.database_primary.strip().lower() in {"postgres", "postgresql", "pg"}

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"production", "prod"}

    def masked_database_url(self) -> str:
        value = self.database_url.strip()
        if not value or "://" not in value:
            return value
        scheme, rest = value.split("://", 1)
        if "@" not in rest:
            return f"{scheme}://{rest}"
        credentials, host = rest.rsplit("@", 1)
        user = credentials.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings(
        project_root=PROJECT_ROOT,
        app_env=_env("APP_ENV", _env("ENV", "development")),
        database_url=_env("DATABASE_URL", ""),
        database_primary=_env("DATABASE_PRIMARY", "postgresql"),
        database_allow_legacy_fallback=_bool_env("DATABASE_ALLOW_LEGACY_FALLBACK", False),
        redis_url=_env("REDIS_URL", "redis://localhost:6379/0"),
        task_execution_mode=_env("TASK_EXECUTION_MODE", "auto").strip().lower() or "auto",
        database_echo=_bool_env("DATABASE_ECHO", False),
        llm_provider=_env("LLM_PROVIDER", "ollama"),
        llm_base_url=_env("LLM_BASE_URL", "http://localhost:11434"),
        llm_model=_env("LLM_MODEL", "qwen3:4b"),
        auth_required=_bool_env("AUTH_REQUIRED", False),
        jwt_secret_key=_env("JWT_SECRET_KEY", "change_me_dev_jwt_secret"),
        jwt_algorithm=_env("JWT_ALGORITHM", "HS256"),
        jwt_access_token_expire_minutes=_int_env("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 1440),
        rag_profile=_env("RAG_PROFILE", "balanced"),
        rag_keyword_limit=_int_env("RAG_KEYWORD_LIMIT", _int_env("RAG_KEYWORD_TOP_K", 25)),
        rag_vector_limit=_int_env("RAG_VECTOR_LIMIT", _int_env("RAG_VECTOR_TOP_K", 40)),
        rag_rerank_candidate_limit=_int_env("RAG_RERANK_CANDIDATE_LIMIT", 12),
        rag_cache_ttl_seconds=_int_env("RAG_CACHE_TTL_SECONDS", 600),
    )
    if settings.is_production and settings.database_allow_legacy_fallback:
        logger.warning("DATABASE_ALLOW_LEGACY_FALLBACK=1 is enabled while APP_ENV=production.")
    if settings.task_execution_mode not in {"auto", "celery", "local_thread"}:
        logger.warning("Invalid TASK_EXECUTION_MODE=%s, expected auto/celery/local_thread.", settings.task_execution_mode)
    if settings.is_production and settings.task_execution_mode == "local_thread":
        logger.warning("TASK_EXECUTION_MODE=local_thread is enabled while APP_ENV=production. Use celery for production.")
    if (settings.is_production or settings.auth_required) and settings.jwt_secret_key in {"", "change_me", "change_me_dev_jwt_secret"}:
        logger.warning("JWT_SECRET_KEY uses a default placeholder while auth is enabled or production mode is active.")
    return settings


def reset_settings_cache() -> None:
    get_settings.cache_clear()

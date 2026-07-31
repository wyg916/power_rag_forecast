from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from config_loader import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
logger = logging.getLogger(__name__)

SUPPORTED_APP_ENVS = {"development", "test", "production"}
APP_ENV_ALIASES = {"dev": "development", "testing": "test", "prod": "production"}
WEAK_JWT_SECRETS = {
    "change_me",
    "change_me_dev_jwt_secret",
    "changeme",
    "default",
    "jwt_secret",
    "secret",
    "your_jwt_secret",
    "your_secret_key",
}
JWT_SECRET_PLACEHOLDER_MARKERS = (
    "${jwt_secret",
    "<jwt_secret",
    "placeholder",
    "replace_me",
    "replace-me",
    "replace_with",
    "replace-with",
)


class SecurityConfigurationError(RuntimeError):
    """Raised when authentication would start with an unsafe configuration."""


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


def _normalize_app_env(value: str) -> str:
    normalized = str(value or "development").strip().lower() or "development"
    return APP_ENV_ALIASES.get(normalized, normalized)


def _is_weak_jwt_secret(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in WEAK_JWT_SECRETS or any(marker in normalized for marker in JWT_SECRET_PLACEHOLDER_MARKERS)


@dataclass(frozen=True)
class Settings:
    project_root: Path
    app_env: str
    database_url: str
    security_database_url: str
    migration_database_url: str
    database_primary: str
    database_allow_legacy_fallback: bool
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str
    task_execution_mode: str
    database_echo: bool
    llm_provider: str
    llm_base_url: str
    llm_model: str
    auth_required: bool
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_access_token_expire_minutes: int
    admin_initialized: bool
    rag_profile: str
    rag_keyword_limit: int
    rag_vector_limit: int
    rag_rerank_candidate_limit: int
    rag_cache_ttl_seconds: int

    @property
    def has_database_url(self) -> bool:
        return bool(self.database_url.strip())

    @property
    def has_security_database_url(self) -> bool:
        return bool(self.security_database_url.strip())

    @property
    def wants_postgres_primary(self) -> bool:
        return self.database_primary.strip().lower() in {"postgres", "postgresql", "pg"}

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

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


def validate_security_settings(settings: Settings) -> None:
    errors: list[str] = []
    if settings.app_env not in SUPPORTED_APP_ENVS:
        errors.append("APP_ENV 必须为 development、test 或 production")

    secret = settings.jwt_secret_key.strip()
    secret_is_weak = _is_weak_jwt_secret(secret)
    if settings.auth_required or settings.is_production:
        if not secret:
            errors.append("缺少 JWT_SECRET_KEY")
        elif secret_is_weak:
            errors.append("JWT_SECRET_KEY 使用禁止的默认弱值")
    if settings.is_production:
        if not settings.auth_required:
            errors.append("production 必须启用 AUTH_REQUIRED")
        if secret and len(secret) < 32:
            errors.append("production 的 JWT_SECRET_KEY 长度必须至少为 32 个字符")
        if not settings.admin_initialized:
            errors.append("production 缺少 ADMIN_INITIALIZED=1；请先通过受控流程初始化管理员")
        if not settings.database_url.strip():
            errors.append("production 缺少普通运行身份 DATABASE_URL")
        if not settings.security_database_url.strip():
            errors.append("production 缺少独立安全仓储身份 SECURITY_DATABASE_URL")
        if settings.database_url.strip() == settings.security_database_url.strip():
            errors.append("production 的 DATABASE_URL 与 SECURITY_DATABASE_URL 必须分离")
        if settings.migration_database_url.strip() and settings.migration_database_url.strip() == settings.database_url.strip():
            errors.append("MIGRATION_DATABASE_URL 不得与普通运行 DATABASE_URL 相同")
    if (settings.auth_required or settings.is_production) and settings.jwt_algorithm.upper() != "HS256":
        errors.append("JWT_ALGORITHM 必须为 HS256")
    if settings.database_url.strip() and not settings.is_test and not settings.security_database_url.strip():
        errors.append("配置 DATABASE_URL 时必须同时配置独立 SECURITY_DATABASE_URL")
    if settings.database_url.strip() and settings.database_url.strip() == settings.security_database_url.strip():
        errors.append("DATABASE_URL 与 SECURITY_DATABASE_URL 不得使用同一连接")
    if settings.migration_database_url.strip() and settings.migration_database_url.strip() == settings.database_url.strip():
        errors.append("MIGRATION_DATABASE_URL 不得与普通运行 DATABASE_URL 相同")

    if errors:
        raise SecurityConfigurationError("安全配置无效：" + "；".join(errors))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    app_env = _normalize_app_env(_env("APP_ENV", _env("ENV", "development")))
    production_default = app_env == "production"
    settings = Settings(
        project_root=PROJECT_ROOT,
        app_env=app_env,
        database_url=_env("DATABASE_URL", ""),
        security_database_url=_env("SECURITY_DATABASE_URL", ""),
        migration_database_url=_env("MIGRATION_DATABASE_URL", ""),
        database_primary=_env("DATABASE_PRIMARY", "postgresql"),
        database_allow_legacy_fallback=_bool_env("DATABASE_ALLOW_LEGACY_FALLBACK", False),
        redis_url=_env("REDIS_URL", "redis://localhost:6379/0"),
        celery_broker_url=_env("CELERY_BROKER_URL", _env("REDIS_URL", "redis://localhost:6379/0")),
        celery_result_backend=_env("CELERY_RESULT_BACKEND", _env("REDIS_URL", "redis://localhost:6379/0")),
        task_execution_mode=_env("TASK_EXECUTION_MODE", "auto").strip().lower() or "auto",
        database_echo=_bool_env("DATABASE_ECHO", False),
        llm_provider=_env("LLM_PROVIDER", "ollama"),
        llm_base_url=_env("LLM_BASE_URL", "http://localhost:11434"),
        llm_model=_env("LLM_MODEL", "qwen3:4b"),
        auth_required=_bool_env("AUTH_REQUIRED", production_default),
        jwt_secret_key=_env("JWT_SECRET_KEY", ""),
        jwt_algorithm=_env("JWT_ALGORITHM", "HS256"),
        jwt_access_token_expire_minutes=_int_env("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 1440),
        admin_initialized=_bool_env("ADMIN_INITIALIZED", False),
        rag_profile=_env("RAG_PROFILE", "balanced"),
        rag_keyword_limit=_int_env("RAG_KEYWORD_LIMIT", _int_env("RAG_KEYWORD_TOP_K", 25)),
        rag_vector_limit=_int_env("RAG_VECTOR_LIMIT", _int_env("RAG_VECTOR_TOP_K", 40)),
        rag_rerank_candidate_limit=_int_env("RAG_RERANK_CANDIDATE_LIMIT", 12),
        rag_cache_ttl_seconds=_int_env("RAG_CACHE_TTL_SECONDS", 600),
    )
    validate_security_settings(settings)
    if settings.is_production and settings.database_allow_legacy_fallback:
        logger.warning("DATABASE_ALLOW_LEGACY_FALLBACK=1 is enabled while APP_ENV=production.")
    if settings.task_execution_mode not in {"auto", "celery", "local_thread"}:
        logger.warning("Invalid TASK_EXECUTION_MODE=%s, expected auto/celery/local_thread.", settings.task_execution_mode)
    if settings.is_production and settings.task_execution_mode == "local_thread":
        logger.warning("TASK_EXECUTION_MODE=local_thread is enabled while APP_ENV=production. Use celery for production.")

    return settings


def reset_settings_cache() -> None:
    get_settings.cache_clear()

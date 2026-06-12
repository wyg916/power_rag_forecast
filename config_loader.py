# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "llm_service_config.yaml"
DEFAULT_ENV_PATH = ROOT_DIR / ".env"

_ENV_LOADED = False


def load_dotenv(env_path: Path | None = None) -> None:
    """Load simple KEY=VALUE pairs from .env without overriding real env vars."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True

    path = env_path or DEFAULT_ENV_PATH
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (key not in os.environ or os.environ.get(key, "") == ""):
            os.environ[key] = value


def _env(name: str, default: Any = None) -> Any:
    load_dotenv()
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def _env_int(name: str, default: int) -> int:
    value = _env(name, default)
    try:
        return int(value)
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    value = _env(name, default)
    try:
        return float(value)
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = str(_env(name, str(int(default)))).strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _normalize_api_mode(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"ollama_native", "native"}:
        return "native"
    if normalized in {"openai", "openai_compat", "openai-compatible"}:
        return "openai_compat"
    return value or "native"


def apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    load_dotenv()

    db = config.setdefault("database", {})
    db["enabled"] = _env_bool("DB_ENABLED", bool(db.get("enabled", False)))
    db["host"] = _env("DB_HOST", db.get("host", "localhost"))
    db["port"] = _env_int("DB_PORT", int(db.get("port", 3306)))
    db["database"] = _env("DB_NAME", db.get("database", ""))
    db["user"] = _env("DB_USER", db.get("user", ""))
    db["password"] = _env("DB_PASSWORD", db.get("password", ""))
    db["charset"] = _env("DB_CHARSET", db.get("charset", "utf8mb4"))
    db["connect_timeout"] = _env_int("DB_CONNECT_TIMEOUT", int(db.get("connect_timeout", 10)))

    llm = config.setdefault("llm", {})
    llm["provider"] = _env("LLM_PROVIDER", llm.get("provider", "ollama"))
    llm["api_mode"] = _normalize_api_mode(_env("LLM_API_MODE", llm.get("api_mode", "native")))
    llm["base_url"] = _env("LLM_BASE_URL", llm.get("base_url", "http://localhost:11434"))
    llm["api_key"] = _env("LLM_API_KEY", llm.get("api_key", ""))
    llm["model"] = _env("LLM_MODEL", llm.get("model", "qwen3:4b"))
    llm["temperature"] = _env_float("LLM_TEMPERATURE", float(llm.get("temperature", 0.2)))
    llm["max_tokens"] = _env_int("LLM_MAX_TOKENS", int(llm.get("max_tokens", 2200)))
    llm["timeout_seconds"] = _env_int("LLM_TIMEOUT", int(llm.get("timeout_seconds", 240)))
    llm["auto_pull"] = _env_bool("LLM_AUTO_PULL", bool(llm.get("auto_pull", True)))

    market = config.setdefault("market", {})
    market["pjm_subscription_key"] = _env("PJM_SUBSCRIPTION_KEY", market.get("pjm_subscription_key", ""))
    market["pjm_node_id"] = _env_int("PJM_NODE_ID", int(market.get("pjm_node_id", 34964545)))
    market["pjm_node_name"] = _env("PJM_NODE_NAME", market.get("pjm_node_name", "DOM"))
    market["pjm_region"] = _env("PJM_REGION", market.get("pjm_region", "DOM"))
    market["pjm_auto_discover_subscription_key"] = _env_bool(
        "PJM_AUTO_DISCOVER_SUBSCRIPTION_KEY",
        bool(market.get("pjm_auto_discover_subscription_key", True)),
    )
    market["pjm_settings_url"] = _env(
        "PJM_SETTINGS_URL",
        market.get("pjm_settings_url", "https://dataminer2.pjm.com/config/settings.json"),
    )
    market["weather_lat"] = _env_float("WEATHER_LAT", float(market.get("weather_lat", 37.5407)))
    market["weather_lon"] = _env_float("WEATHER_LON", float(market.get("weather_lon", -77.4360)))
    market["weather_point_name"] = _env("WEATHER_POINT_NAME", market.get("weather_point_name", "Richmond, Virginia"))
    market["timezone"] = _env("MARKET_TIMEZONE", market.get("timezone", "America/New_York"))

    model_learning = config.setdefault("model_learning", {})
    model_learning["active_artifact_path"] = _env(
        "ACTIVE_MODEL_ARTIFACT_PATH",
        model_learning.get("active_artifact_path", ""),
    )
    model_learning["bias_correction_enabled"] = _env_bool(
        "BIAS_CORRECTION_ENABLED",
        bool(model_learning.get("bias_correction_enabled", True)),
    )
    model_learning["min_error_memory_samples"] = _env_int(
        "BIAS_CORRECTION_MIN_SAMPLES",
        int(model_learning.get("min_error_memory_samples", 10)),
    )
    model_learning["max_bias_adjustment"] = _env_float(
        "BIAS_CORRECTION_MAX_ADJUSTMENT",
        float(model_learning.get("max_bias_adjustment", 10.0)),
    )

    paths = config.setdefault("paths", {})
    automation_root = _env("PIPELINE_OUTPUT_ROOT", None)
    if automation_root:
        paths["automation_dir"] = automation_root
        paths["current_dir"] = f"{automation_root}/current"
        paths["archive_dir"] = f"{automation_root}/archive"
        paths["dispatch_dir"] = f"{automation_root}/dispatch"
        paths["log_dir"] = f"{automation_root}/logs"
    paths["final_output_root_dir"] = _env(
        "FINAL_OUTPUT_ROOT",
        paths.get("final_output_root_dir", "全流程预测结果数据存放"),
    )

    return config


def load_config(config_path: Path | str | None = None) -> dict[str, Any]:
    config_file = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    with config_file.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    return apply_env_overrides(config)


def require_secret(value: str | None, name: str, hint: str) -> str:
    if not value or str(value).strip() in {"your_password_here", "your_pjm_subscription_key_here"}:
        raise RuntimeError(f"未配置 {name}。请在 .env 或系统环境变量中设置 {hint}。")
    return str(value).strip()

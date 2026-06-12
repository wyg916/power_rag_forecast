from __future__ import annotations

import logging
import os
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.core.redaction import mask_secret_fields


PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RECENT_EXCEPTIONS: deque[dict[str, Any]] = deque(maxlen=50)
_LOGGING_CONFIGURED = False


def configure_app_logging() -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return
    log_dir = PROJECT_ROOT / "output" / "runtime_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("backend.app")
    logger.setLevel(logging.INFO)
    if not any(getattr(handler, "name", "") == "backend_app_file" for handler in logger.handlers):
        handler = logging.FileHandler(log_dir / "backend_app.log", encoding="utf-8")
        handler.name = "backend_app_file"
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        logger.addHandler(handler)
    _LOGGING_CONFIGURED = True


def app_logger() -> logging.Logger:
    configure_app_logging()
    return logging.getLogger("backend.app")


def log_suppressed_exception(context: str, exc: BaseException, **metadata: Any) -> str:
    configure_app_logging()
    message = str(mask_secret_fields(f"{type(exc).__name__}: {exc}"))
    safe_metadata = mask_secret_fields(metadata)
    event = {
        "time": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "context": context,
        "message": message,
        "metadata": safe_metadata,
        "pid": os.getpid(),
    }
    _RECENT_EXCEPTIONS.append(event)
    app_logger().warning("%s failed: %s", context, message, exc_info=True, extra={"metadata": safe_metadata})
    return message


def recent_suppressed_exceptions(limit: int = 20) -> list[dict[str, Any]]:
    return list(_RECENT_EXCEPTIONS)[-max(1, int(limit)) :]

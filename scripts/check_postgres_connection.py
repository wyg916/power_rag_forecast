from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _build_database_url() -> str:
    value = os.environ.get("DATABASE_URL", "").strip()
    if value:
        return value
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1").strip()
    port = os.environ.get("POSTGRES_PORT", "5432").strip()
    user = os.environ.get("POSTGRES_USER", "postgres").strip()
    password = os.environ.get("POSTGRES_PASSWORD", "")
    db = os.environ.get("POSTGRES_DB", "postgres").strip()
    if not password:
        return ""
    return f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{db}"


def _masked_info(database_url: str) -> dict[str, Any]:
    url = make_url(database_url)
    return {
        "driver": url.drivername,
        "host": url.host or "",
        "port": url.port or 5432,
        "user": url.username or "",
        "db": url.database or "",
        "password": "******" if url.password else "",
    }


def check_connection(database_url: str) -> dict[str, Any]:
    info = _masked_info(database_url)
    engine = create_engine(database_url, pool_pre_ping=True, future=True)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
        current_database = conn.execute(text("SELECT current_database()")).scalar()
        current_user = conn.execute(text("SELECT current_user")).scalar()
        one = conn.execute(text("SELECT 1")).scalar()
    return {
        "status": "ok",
        "connection": info,
        "checks": {
            "select_1": one == 1,
            "current_database": current_database,
            "current_user": current_user,
            "version": version,
        },
    }


def main() -> int:
    database_url = _build_database_url()
    if not database_url:
        print(json.dumps({"status": "skipped", "reason": "DATABASE_URL or POSTGRES_PASSWORD is not set."}, ensure_ascii=False, indent=2))
        return 0
    try:
        result = check_connection(database_url)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    except Exception as exc:
        secret = os.environ.get("POSTGRES_PASSWORD", "")
        error_text = str(exc).replace(secret, "******") if secret else str(exc)
        print(
            json.dumps(
                {
                    "status": "failed",
                    "connection": _masked_info(database_url),
                    "error_type": type(exc).__name__,
                    "error": error_text,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

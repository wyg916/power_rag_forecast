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
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.redaction import safe_exception_summary


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


def _safe_masked_info(database_url: str) -> dict[str, Any]:
    try:
        return _masked_info(database_url)
    except Exception:
        return {"driver": "unparsed", "host": "", "port": "", "user": "", "db": "", "password": ""}


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
        try:
            secret = make_url(database_url).password or ""
        except Exception:
            secret = os.environ.get("POSTGRES_PASSWORD", "")
        print(
            json.dumps(
                {
                    "status": "failed",
                    "connection": _safe_masked_info(database_url),
                    "error": safe_exception_summary(exc, extra_secrets=(secret,)),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

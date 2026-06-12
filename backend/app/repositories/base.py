from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app.core.config import get_settings
from backend.app.db.session import get_engine
from backend.app.observability import log_suppressed_exception


def postgres_engine() -> Engine | None:
    if not get_settings().has_database_url:
        return None
    try:
        engine = get_engine()
        if engine.dialect.name != "postgresql":
            return None
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception as exc:
        log_suppressed_exception("repositories.postgres_engine", exc)
        return None


def is_postgres_engine(engine: Engine | None) -> bool:
    return bool(engine is not None and engine.dialect.name == "postgresql")


def jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def loads_json(value: Any, default: Any = None) -> Any:
    if value is None:
        return {} if default is None else default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception as exc:
            log_suppressed_exception("repositories.loads_json", exc, value_preview=value[:200])
            return {} if default is None else default
    return value


def dumps_json(value: Any) -> str:
    return json.dumps(jsonable(value), ensure_ascii=False, default=str)


def mapping_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    return jsonable(dict(row))


def mapping_list(rows: Any) -> list[dict[str, Any]]:
    return [mapping_dict(row) for row in rows or []]

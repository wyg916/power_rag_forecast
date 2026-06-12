from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import text

from .base import jsonable, loads_json, mapping_dict, postgres_engine


def report_status_from_postgres(report_id: str = "latest") -> dict[str, Any] | None:
    engine = postgres_engine()
    if engine is None:
        return None
    try:
        with engine.connect() as conn:
            if report_id and report_id != "latest":
                row = conn.execute(
                    text(
                        """
                        SELECT report_id, run_id, title, status, report_type, file_path,
                               metadata_json, content_json, generated_at, created_at, updated_at
                        FROM report_runs
                        WHERE report_id = :report_id
                        LIMIT 1
                        """
                    ),
                    {"report_id": report_id},
                ).mappings().first()
            else:
                row = conn.execute(
                    text(
                        """
                        SELECT report_id, run_id, title, status, report_type, file_path,
                               metadata_json, content_json, generated_at, created_at, updated_at
                        FROM report_runs
                        ORDER BY COALESCE(generated_at, updated_at, created_at) DESC, report_id DESC
                        LIMIT 1
                        """
                    )
                ).mappings().first()
    except Exception:
        return None
    if row is None:
        return None
    data = mapping_dict(row)
    file_path = str(data.get("file_path") or "")
    metadata = loads_json(data.get("metadata_json"), default={})
    content = loads_json(data.get("content_json"), default={})
    return {
        "report_id": data.get("report_id"),
        "run_id": data.get("run_id"),
        "available": bool(file_path and Path(file_path).exists()) or bool(content),
        "report_path": file_path,
        "generated_at": data.get("generated_at") or data.get("updated_at") or data.get("created_at"),
        "fallback_used": False,
        "summary": content if isinstance(content, dict) else {},
        "metadata": metadata if isinstance(metadata, dict) else {},
        "status": data.get("status"),
        "source": "postgresql.report_runs",
    }

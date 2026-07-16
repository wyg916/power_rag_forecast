from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import text

from .base import jsonable, loads_json, mapping_dict, postgres_engine


def _review_columns(engine) -> set[str]:
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'report_reviews'
                    """
                )
            ).mappings().all()
        return {str(row.get("column_name")) for row in rows}
    except Exception:
        return set()


def _latest_review_map(engine, report_ids: list[str]) -> dict[str, dict[str, Any]]:
    ids = [str(item) for item in report_ids if item]
    if not ids:
        return {}
    columns = _review_columns(engine)
    status_col = "status" if "status" in columns else "action"
    comment_col = "review_comment" if "review_comment" in columns else "comment"
    updated_col = "updated_at" if "updated_at" in columns else "created_at"
    values: dict[str, dict[str, Any]] = {}
    with engine.connect() as conn:
        for report_id in ids:
            row = conn.execute(
                text(
                    f"""
                    SELECT report_id, {status_col} AS review_status, reviewer,
                           {comment_col} AS review_comment, created_at, {updated_col} AS updated_at
                    FROM report_reviews
                    WHERE report_id = :report_id
                    ORDER BY {updated_col} DESC, created_at DESC
                    LIMIT 1
                    """
                ),
                {"report_id": report_id},
            ).mappings().first()
            if row:
                values[report_id] = mapping_dict(row)
    return values


def _public_report_row(row: dict[str, Any], review: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = loads_json(row.get("metadata_json"), default={})
    content = loads_json(row.get("content_json"), default={})
    status = str((review or {}).get("review_status") or row.get("status") or "draft")
    file_path = str(row.get("file_path") or "")
    return {
        "report_id": row.get("report_id"),
        "run_id": row.get("run_id"),
        "title": row.get("title") or row.get("report_id"),
        "status": status,
        "report_type": row.get("report_type") or metadata.get("report_type") or "daily",
        "file_path": file_path,
        "available": bool(file_path and Path(file_path).exists()) or bool(content),
        "metadata": metadata if isinstance(metadata, dict) else {},
        "summary": content if isinstance(content, dict) else {},
        "generated_at": row.get("generated_at") or row.get("updated_at") or row.get("created_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "latest_review": review or {},
        "source": "postgresql.report_runs",
    }


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


def list_reports_from_postgres(
    *,
    keyword: str = "",
    report_type: str = "",
    status: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any] | None:
    engine = postgres_engine()
    if engine is None:
        return None
    where = []
    params: dict[str, Any] = {"limit": max(1, min(int(page_size or 20), 100)), "offset": max(0, (int(page or 1) - 1) * int(page_size or 20))}
    if keyword:
        where.append("(report_id ILIKE :keyword OR title ILIKE :keyword OR run_id ILIKE :keyword)")
        params["keyword"] = f"%{keyword}%"
    if report_type:
        where.append("report_type = :report_type")
        params["report_type"] = report_type
    if status:
        where.append("status = :status")
        params["status"] = status
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    try:
        with engine.connect() as conn:
            total = conn.execute(text(f"SELECT COUNT(*) FROM report_runs {where_sql}"), params).scalar_one()
            rows = conn.execute(
                text(
                    f"""
                    SELECT report_id, run_id, title, status, report_type, file_path,
                           metadata_json, content_json, generated_at, created_at, updated_at
                    FROM report_runs
                    {where_sql}
                    ORDER BY COALESCE(generated_at, updated_at, created_at) DESC, report_id DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            ).mappings().all()
    except Exception:
        return None
    values = [mapping_dict(row) for row in rows]
    reviews = _latest_review_map(engine, [str(row.get("report_id")) for row in values])
    return {
        "items": [_public_report_row(row, reviews.get(str(row.get("report_id")))) for row in values],
        "total": int(total or 0),
        "page": int(page or 1),
        "page_size": params["limit"],
        "source": "postgresql.report_runs",
    }


def report_summary_from_postgres() -> dict[str, Any] | None:
    payload = list_reports_from_postgres(page=1, page_size=500)
    if payload is None:
        return None
    items = payload.get("items") or []
    today = 0
    pending = 0
    published = 0
    rejected = 0
    for item in items:
        generated = str(item.get("generated_at") or "")[:10]
        status = str(item.get("status") or "")
        if generated == date.today().isoformat():
            today += 1
        if status in {"draft", "ready", "pending", "reviewing"}:
            pending += 1
        if status in {"published", "approved"}:
            published += 1
        if status == "rejected":
            rejected += 1
    return {
        "today_generated": today,
        "pending_review": pending,
        "published": published,
        "rejected": rejected,
        "total": payload.get("total") or len(items),
        "source": payload.get("source"),
    }

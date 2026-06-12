from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "tests" / "productization" / "output"


def mask_url(value: str) -> str:
    parts = urlsplit(value or "")
    netloc = parts.netloc
    if "@" in netloc:
        credentials, host = netloc.rsplit("@", 1)
        user = credentials.split(":", 1)[0]
        netloc = f"{user}:***@{host}" if user else f"***@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def write_reports(report: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "celery_worker_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Celery Worker Health Check",
        "",
        f"- generated_at: {report.get('generated_at')}",
        f"- status: {report.get('status')}",
        f"- broker_url: {report.get('broker_url')}",
        f"- worker_count: {report.get('worker_count')}",
        f"- health_task_status: {report.get('health_task_status')}",
        f"- message: {report.get('message')}",
    ]
    (OUTPUT_DIR / "celery_worker_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    from backend.app.core.config import get_settings

    settings = get_settings()
    report = {
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "broker_url": mask_url(settings.redis_url),
        "status": "unknown",
        "worker_count": 0,
        "workers": [],
        "health_task_status": "not_run",
        "health_task_result": None,
        "message": "",
    }
    try:
        from backend.app.workers.celery_app import celery_app

        if celery_app is None:
            report.update({"status": "skipped", "message": "celery package is not available"})
            write_reports(report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        ping_rows = celery_app.control.ping(timeout=2) or []
        report["workers"] = ping_rows
        report["worker_count"] = len(ping_rows)
        if not ping_rows:
            report.update({"status": "failed_with_clear_reason", "message": "no online celery worker responded"})
            write_reports(report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1
        from backend.app.workers.tasks import health_check_task

        async_result = health_check_task.delay()
        result = async_result.get(timeout=10)
        report.update(
            {
                "status": "pass",
                "health_task_status": "pass",
                "health_task_result": result,
                "message": "celery worker health task completed",
            }
        )
        write_reports(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        report.update({"status": "fail", "message": f"{type(exc).__name__}: {exc}"})
        write_reports(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

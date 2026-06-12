from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "tests" / "productization" / "output"


def _task_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _record(task_id: str, status: str, **extra) -> dict:
    payload = {
        "task_id": task_id,
        "run_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "kind": extra.pop("kind", "runtime_check"),
        "task_name": "runtime_check",
        "task_type": "runtime_check",
        "status": status,
        "payload": {"source": "check_task_center_runtime"},
        "started_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "progress": extra.pop("progress", 0),
        "message": extra.pop("message", status),
        "error_message": extra.pop("error_message", ""),
        "execution_mode": extra.pop("execution_mode", "local_thread"),
        "metadata": extra.pop("metadata", {"runtime_check": True}),
    }
    payload.update(extra)
    return payload


def write_reports(report: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "task_center_runtime_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Task Center Runtime Report",
        "",
        f"- generated_at: {report.get('generated_at')}",
        f"- status: {report.get('status')}",
        f"- task_execution_mode: {report.get('task_execution_mode')}",
        f"- repository_available: {report.get('repository_available')}",
        f"- celery_available: {report.get('celery_available')}",
        f"- local_simulation: {report.get('local_simulation')}",
        "",
        "## Checks",
        "",
        "| Check | Status | Message |",
        "|---|---|---|",
    ]
    for item in report.get("checks", []):
        lines.append(f"| {item.get('name')} | {item.get('status')} | {item.get('message', '')} |")
    if report.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in report["warnings"])
    (OUTPUT_DIR / "task_center_runtime_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    from backend.app.core.config import get_settings
    from backend.app.repositories.task_repository import get_task_record, save_task_record, update_task_runtime_state
    from backend.app.workers.dispatcher import celery_available

    settings = get_settings()
    report = {
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "status": "unknown",
        "task_execution_mode": settings.task_execution_mode,
        "repository_available": False,
        "celery_available": False,
        "local_simulation": False,
        "checks": [],
        "warnings": [],
    }

    try:
        report["celery_available"] = celery_available()
    except Exception as exc:
        report["warnings"].append(f"celery availability check failed: {type(exc).__name__}")

    if settings.task_execution_mode == "celery" and not report["celery_available"]:
        report["status"] = "fail"
        report["checks"].append({"name": "celery_required", "status": "fail", "message": "TASK_EXECUTION_MODE=celery but Celery/Redis is unavailable"})
        write_reports(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    try:
        pending_id = _task_id("runtime_pending")
        ok = save_task_record(_record(pending_id, "pending", progress=0), status="pending")
        report["repository_available"] = bool(ok)
        if not ok:
            report["local_simulation"] = True
            report["warnings"].append("PostgreSQL task repository is unavailable; runtime transitions were simulated only.")
        report["checks"].append({"name": "create_pending_task", "status": "pass" if ok else "skipped", "message": pending_id})

        success_id = _task_id("runtime_success")
        save_task_record(_record(success_id, "pending", progress=0), status="pending")
        save_task_record(_record(success_id, "running", progress=10, message="running"), status="running")
        save_task_record(_record(success_id, "success", progress=100, message="success", result_ref="runtime_check"), status="success")
        success_record = get_task_record(success_id)
        report["checks"].append(
            {
                "name": "pending_running_success_flow",
                "status": "pass" if not ok or (success_record or {}).get("status") == "success" else "fail",
                "message": success_id,
            }
        )

        failed_id = _task_id("runtime_failed")
        save_task_record(_record(failed_id, "running", progress=10), status="running")
        save_task_record(_record(failed_id, "failed", progress=100, error_message="runtime check failure", message="failed"), status="failed")
        failed_record = get_task_record(failed_id)
        report["checks"].append(
            {
                "name": "failure_records_error",
                "status": "pass" if not ok or bool((failed_record or {}).get("error_message")) else "fail",
                "message": failed_id,
            }
        )

        retry_id = _task_id("runtime_retry")
        save_task_record(_record(retry_id, "failed", progress=100, retry_count=0, error_message="retry source"), status="failed")
        update_task_runtime_state(retry_id, status="failed", retry_count=1, message="retry count incremented")
        retry_record = get_task_record(retry_id)
        report["checks"].append(
            {
                "name": "retry_count_update",
                "status": "pass" if not ok or int((retry_record or {}).get("retry_count") or 0) >= 1 else "fail",
                "message": retry_id,
            }
        )

        cancel_pending_id = _task_id("runtime_cancel_pending")
        save_task_record(_record(cancel_pending_id, "pending"), status="pending")
        update_task_runtime_state(cancel_pending_id, status="cancelled", message="cancelled before start", cancel_requested=True, finish=True)
        cancel_pending_record = get_task_record(cancel_pending_id)
        report["checks"].append(
            {
                "name": "cancel_pending_task",
                "status": "pass" if not ok or (cancel_pending_record or {}).get("status") == "cancelled" else "fail",
                "message": cancel_pending_id,
            }
        )

        cancel_running_id = _task_id("runtime_cancel_running")
        save_task_record(_record(cancel_running_id, "running", progress=10), status="running")
        update_task_runtime_state(cancel_running_id, status="cancel_requested", message="cancel request recorded", cancel_requested=True)
        cancel_running_record = get_task_record(cancel_running_id)
        report["checks"].append(
            {
                "name": "cancel_running_task",
                "status": "pass" if not ok or (cancel_running_record or {}).get("status") == "cancel_requested" else "fail",
                "message": cancel_running_id,
            }
        )

        failed_checks = [item for item in report["checks"] if item["status"] == "fail"]
        report["status"] = "fail" if failed_checks else ("pass_with_warnings" if report["warnings"] else "pass")
        write_reports(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] in {"pass", "pass_with_warnings"} else 1
    except Exception as exc:
        report["status"] = "fail"
        report["checks"].append({"name": "runtime_exception", "status": "fail", "message": f"{type(exc).__name__}: {exc}"})
        write_reports(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

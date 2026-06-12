from __future__ import annotations

from typing import Any

from ...data_access import report_status


def get_report_summary(run_id: str = "latest", **_: Any) -> dict[str, Any]:
    report = report_status(run_id)
    return {"tool": "get_report_summary", **report}

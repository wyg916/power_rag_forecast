from __future__ import annotations

from pathlib import Path
from typing import Any


def collect_local_output_status(result_table_dir: str | Path) -> dict[str, Any]:
    path = Path(result_table_dir)
    files = sorted(path.glob("*.xlsx")) if path.exists() else []
    return {
        "result_table_dir": str(path),
        "exists": path.exists(),
        "xlsx_count": len(files),
        "latest_mtime": max((f.stat().st_mtime for f in files), default=None),
    }

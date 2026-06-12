from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
OUTPUT_DIR = PROJECT_ROOT / "tests" / "productization" / "output"
REPORT_JSON = OUTPUT_DIR / "stage1_repository_gap_report.json"
REPORT_MD = OUTPUT_DIR / "stage1_repository_gap_report.md"

STAGE1_DOMAINS = {
    "weather_data": {
        "repository": "backend.app.repositories.weather_repository",
        "expected_tables": ["raw_weather"],
        "source_file": "backend/app/stage1_services.py",
        "source_tokens": ["load_weather_forecast_from_postgres", "weather_raw.xlsx"],
    },
    "load_data": {
        "repository": "backend.app.repositories.load_repository",
        "expected_tables": ["raw_load", "raw_forecast_load_selected"],
        "source_file": "backend/app/stage1_services.py",
        "source_tokens": ["load_forecast_load_from_postgres", "forecast_load_selected.xlsx"],
    },
    "market_data": {
        "repository": "backend.app.repositories.market_data_repository",
        "expected_tables": ["raw_market", "raw_da_price"],
        "source_file": "backend/app/stage1_services.py",
        "source_tokens": ["load_market_history_from_postgres", "da_price_raw.xlsx"],
    },
    "renewable_data": {
        "repository": "backend.app.repositories.renewable_repository",
        "expected_tables": ["raw_renewable", "raw_renewable_forecast", "raw_solar_forecast", "raw_wind_forecast"],
        "source_file": "backend/app/stage1_services.py",
        "source_tokens": ["load_renewable_forecast_from_postgres"],
    },
    "feature_importance": {
        "repository": "backend.app.repositories.feature_repository",
        "expected_tables": ["model_feature_importance", "feature_importance"],
        "source_file": "backend/app/stage1_services.py",
        "source_tokens": ["load_feature_importance_from_postgres", "13_"],
    },
    "report_review": {
        "repository": "backend.app.repositories.report_repository",
        "expected_tables": ["report_reviews"],
        "source_file": "backend/app/platform_services.py",
        "source_tokens": ["report_reviews", "web_report_reviews.json"],
    },
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _migration_tables() -> set[str]:
    text = "\n".join(_read(path) for path in sorted((PROJECT_ROOT / "migrations" / "versions").glob("*.py")))
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)", text, flags=re.IGNORECASE))


def _runtime_table_exists(table_name: str) -> bool:
    try:
        from backend.app.repositories.market_data_repository import table_exists

        return bool(table_exists(table_name))
    except Exception:
        return False


def _repository_importable(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except Exception:
        return False


def build_stage1_gap_report() -> dict[str, Any]:
    migration_tables = _migration_tables()
    domains: dict[str, Any] = {}
    for domain, spec in STAGE1_DOMAINS.items():
        repo_importable = _repository_importable(spec["repository"])
        table_states = [
            {
                "name": table,
                "declared_in_migration": table in migration_tables,
                "exists_runtime": _runtime_table_exists(table),
            }
            for table in spec["expected_tables"]
        ]
        source_text = _read(PROJECT_ROOT / spec["source_file"])
        source_hits = [token for token in spec["source_tokens"] if token in source_text]
        any_runtime_table = any(item["exists_runtime"] for item in table_states)
        any_migration_table = any(item["declared_in_migration"] for item in table_states)
        if any_runtime_table:
            status = "postgresql_ready"
        elif repo_importable and any_migration_table:
            status = "postgresql_path_ready_pending_data"
        elif repo_importable:
            status = "pending_schema_or_data_migration"
        else:
            status = "fallback_only"
        domains[domain] = {
            "status": status,
            "repository": spec["repository"],
            "repository_importable": repo_importable,
            "tables": table_states,
            "source_file": spec["source_file"],
            "source_hits": source_hits,
            "recommendation": _recommendation(domain, status),
        }
    return {
        "status": "stage1_gap_known",
        "domains": domains,
        "summary": {
            "postgresql_ready": sum(1 for item in domains.values() if item["status"] == "postgresql_ready"),
            "postgresql_path_ready_pending_data": sum(1 for item in domains.values() if item["status"] == "postgresql_path_ready_pending_data"),
            "pending_schema_or_data_migration": sum(1 for item in domains.values() if item["status"] == "pending_schema_or_data_migration"),
            "fallback_only": sum(1 for item in domains.values() if item["status"] == "fallback_only"),
        },
    }


def _recommendation(domain: str, status: str) -> str:
    if status == "postgresql_ready":
        return "Keep PostgreSQL as the first path and keep legacy fallback disabled in production."
    if domain == "report_review":
        return "Report review table is declared by migration; keep local JSON only as development fallback."
    return "Add or migrate the related raw table data before removing legacy file fallback."


def _md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines)


def write_stage1_gap_reports(report: dict[str, Any] | None = None) -> dict[str, Any]:
    data = report or build_stage1_gap_report()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    rows = []
    for domain, item in data["domains"].items():
        tables = ", ".join(
            f"{table['name']}[migration={table['declared_in_migration']}, runtime={table['exists_runtime']}]"
            for table in item["tables"]
        )
        rows.append([domain, item["status"], item["repository_importable"], tables, item["recommendation"]])
    lines = [
        "# Stage1 Repository Gap 报告",
        "",
        f"- 总体状态：`{data['status']}`",
        f"- 统计：{json.dumps(data['summary'], ensure_ascii=False)}",
        "",
        _md_table(["领域", "状态", "repository 可导入", "表状态", "建议"], rows),
    ]
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return data


if __name__ == "__main__":
    result = write_stage1_gap_reports()
    print(json.dumps({"status": result["status"], "summary": result["summary"]}, ensure_ascii=False, indent=2))

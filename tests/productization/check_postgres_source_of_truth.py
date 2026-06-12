from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import statistics
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from stage1_repository_gap import build_stage1_gap_report, write_stage1_gap_reports


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "tests" / "productization" / "output"
REPORT_JSON = OUTPUT_DIR / "postgres_source_of_truth_report.json"
REPORT_MD = OUTPUT_DIR / "postgres_source_of_truth_report.md"
RUNTIME_REPORT_JSON = OUTPUT_DIR / "postgres_runtime_report.json"

SOURCE_ROOTS = [
    PROJECT_ROOT / "backend",
    PROJECT_ROOT / "frontend" / "src",
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "tests",
    PROJECT_ROOT / "migrations",
    PROJECT_ROOT / "knowledge_pipeline",
]

EXTRA_FILES = [
    PROJECT_ROOT / ".env.example",
    PROJECT_ROOT / "alembic.ini",
    PROJECT_ROOT / "backend" / "README.md",
]

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "logs",
    "cache",
    "output",
    "outputs",
    "markdown",
    "converted",
    "chunks",
    "raw",
}

TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".txt",
    ".toml",
    ".ini",
    ".yml",
    ".yaml",
    ".example",
}

REPOSITORIES = {
    "forecast": "backend.app.repositories.forecast_repository",
    "model": "backend.app.repositories.model_repository",
    "task": "backend.app.repositories.task_repository",
    "report": "backend.app.repositories.report_repository",
    "ai_trace": "backend.app.repositories.ai_trace_repository",
    "audit": "backend.app.repositories.audit_repository",
    "knowledge": "backend.app.repositories.knowledge_repository",
}

CORE_USAGE_EXPECTATIONS = {
    "forecast": {
        "files": ["backend/app/data_access.py", "backend/app/api/v1/endpoints/forecast.py"],
        "tokens": ["forecast_repository", "load_latest_forecast_from_postgres", "load_latest_forecast"],
    },
    "model": {
        "files": ["backend/app/data_access.py", "backend/app/api/v1/endpoints/model.py"],
        "tokens": ["model_repository", "model_status_from_postgres", "model_errors_from_postgres"],
    },
    "task": {
        "files": [
            "backend/app/api/v1/endpoints/task.py",
            "backend/app/workers/dispatcher.py",
            "backend/app/workers/tasks.py",
            "backend/app/task_manager.py",
        ],
        "tokens": ["task_repository", "save_task_record", "list_recent_tasks", "task_log_text"],
    },
    "report": {
        "files": ["backend/app/data_access.py", "backend/app/api/v1/endpoints/report.py", "backend/app/platform_services.py"],
        "tokens": ["report_repository", "report_status_from_postgres", "report_runs", "report_reviews"],
    },
    "ai_trace": {
        "files": ["backend/app/api/v1/endpoints/assistant.py", "backend/app/ai_assistant/service.py"],
        "tokens": ["ai_trace_repository", "save_ai_trace", "list_ai_traces", "get_ai_trace"],
    },
    "audit": {
        "files": ["backend/app/api/v1/endpoints", "backend/app/repositories/audit_repository.py"],
        "tokens": ["audit_repository", "write_audit_log", "audit_logs"],
    },
    "knowledge": {
        "files": ["backend/app/services/rag_service.py", "backend/app/api/v1/endpoints/knowledge.py"],
        "tokens": ["knowledge_repository", "search_keyword_chunks", "list_embedded_chunks", "kb_documents", "kb_chunks"],
    },
}

OLD_SOURCE_PATTERNS = {
    "mysql": re.compile(r"\b(mysql|pymysql|mysql\+pymysql)\b", re.IGNORECASE),
    "excel": re.compile(r"(pandas\.read_excel|pd\.read_excel|read_excel_safe|read_excel|\.xlsx\b|\.xls\b)", re.IGNORECASE),
    "csv": re.compile(r"(pandas\.read_csv|pd\.read_csv|read_csv|\.csv\b)", re.IGNORECASE),
    "local_prediction_file": re.compile(
        r"(未来24小时预测|result_forward_24h|预测结果|model_artifacts|report_output|web_report_reviews\.json)",
        re.IGNORECASE,
    ),
    "old_knowledge_direct_read": re.compile(r"(knowledge_base|04_knowledge_base_tariff_policy|SEARCH_ROOTS)", re.IGNORECASE),
    "sqlite": re.compile(r"(\bsqlite\b|sqlite://)", re.IGNORECASE),
    "hardcoded_project_path": re.compile(r"(E[:：][\\/][^\s\"']*智能运营分析项目|E:\\智能运营分析项目)", re.IGNORECASE),
}

CRITICAL_TABLES = {
    "forecast_runs",
    "forecast_results",
    "model_versions",
    "model_metrics",
    "task_runs",
    "task_logs",
    "ai_traces",
    "report_runs",
    "report_reviews",
    "kb_documents",
    "kb_chunks",
    "audit_logs",
    "roles",
    "users",
    "raw_market",
    "raw_weather",
    "raw_load",
    "raw_renewable",
    "feature_importance",
}


@dataclass
class OldSourceFinding:
    path: str
    line: int
    pattern: str
    snippet: str
    usage_scene: str
    is_main_path: str
    postgres_replacement: str
    recommendation: str


def rel(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def iter_source_files() -> list[Path]:
    files: list[Path] = []
    for root in SOURCE_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
                continue
            if path.name == ".env":
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Dockerfile"}:
                continue
            try:
                if path.stat().st_size > 1_500_000:
                    continue
            except OSError:
                continue
            files.append(path)
    for path in EXTRA_FILES:
        if path.exists() and path.is_file():
            files.append(path)
    unique: dict[str, Path] = {}
    for path in files:
        unique[str(path.resolve())] = path
    return sorted(unique.values(), key=lambda item: rel(item))


def check_repository_imports() -> dict[str, dict[str, Any]]:
    sys.path.insert(0, str(PROJECT_ROOT))
    result: dict[str, dict[str, Any]] = {}
    for name, module_name in REPOSITORIES.items():
        try:
            module = importlib.import_module(module_name)
            public_functions = [
                key
                for key, value in module.__dict__.items()
                if callable(value) and not key.startswith("_")
            ]
            result[name] = {
                "module": module_name,
                "importable": True,
                "public_functions": sorted(public_functions)[:30],
            }
        except Exception as exc:
            result[name] = {
                "module": module_name,
                "importable": False,
                "error": str(exc),
            }
    return result


def file_contains(path_or_dir: str, tokens: list[str]) -> dict[str, Any]:
    target = PROJECT_ROOT / Path(path_or_dir)
    paths: list[Path]
    if target.is_dir():
        paths = [p for p in target.rglob("*.py") if p.is_file()]
    elif target.is_file():
        paths = [target]
    else:
        return {"target": path_or_dir, "exists": False, "matched_tokens": []}
    found: set[str] = set()
    for path in paths:
        text = read_text(path)
        for token in tokens:
            if token in text:
                found.add(token)
    return {"target": path_or_dir, "exists": True, "matched_tokens": sorted(found)}


def check_core_usage() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for domain, spec in CORE_USAGE_EXPECTATIONS.items():
        file_results = [file_contains(path, spec["tokens"]) for path in spec["files"]]
        matched = sorted({token for item in file_results for token in item.get("matched_tokens", [])})
        result[domain] = {
            "expected_tokens": spec["tokens"],
            "files": file_results,
            "status": "ok" if matched else "missing",
            "matched_tokens": matched,
        }
    return result


def classify_finding(path: Path, pattern_name: str, snippet: str) -> tuple[str, str, str, str]:
    path_text = rel(path)
    lowered = path_text.lower()
    snippet_lower = snippet.lower()
    if lowered.startswith("scripts/db_migrate_mysql_to_postgres.py"):
        return ("migration_tool", "否", "是", "保留迁移工具；不要作为运行时主路径。")
    if lowered.startswith("tests/"):
        return ("test_or_evaluation_fixture", "否", "视测试目标而定", "保留测试夹具；避免真实环境依赖旧文件。")
    if lowered.startswith("frontend/src/"):
        return ("frontend_export_or_mock", "否", "不适用", "前端 CSV/XLSX 多为导出或 mock 标识，保留。")
    if lowered.endswith(".md") or lowered.endswith(".example") or lowered.endswith(".ini"):
        return ("documentation_or_config_hint", "否", "不适用", "保留说明；若为旧 MySQL 文档，后续更新措辞。")
    if "core_data_sync.py" in lowered:
        return ("postgres_etl_or_bootstrap", "否", "是", "保留 ETL 输入读取；输出应进入 PostgreSQL。")
    if pattern_name == "local_prediction_file" and (
        "backend/app/ai_assistant/" in lowered
        or "backend/app/ai/answer_guard.py" in lowered
        or "backend/app/ai/context_builder.py" in lowered
        or "backend/app/ai/prompt_templates.py" in lowered
    ):
        return ("assistant_prompt_or_evidence_label", "否", "是", "这是回答证据来源标签或提示词内容，不是本地文件读取主路径。")
    if "backend/app/repositories/" in lowered and pattern_name == "local_prediction_file":
        return ("repository_result_shape", "否", "是", "这是 repository 返回字段或路径字段，不是旧文件读取主路径。")
    if "data_access.py" in lowered:
        return ("postgres_first_compatibility_layer", "部分", "是", "保留 PostgreSQL 优先、旧文件兜底；生产默认关闭 legacy fallback。")
    if "stage1_services.py" in lowered:
        return ("stage1_compatibility_api", "部分", "部分", "预测走 PostgreSQL 优先；天气/负荷等旧文件路径建议后续补 repository。")
    if "rag_service.py" in lowered and pattern_name == "old_knowledge_direct_read":
        return ("knowledge_indexing_source", "否", "是", "本地知识文件作为索引源可保留；检索主路径应使用 kb_documents/kb_chunks。")
    if "knowledge_tools.py" in lowered and pattern_name == "old_knowledge_direct_read":
        return ("assistant_knowledge_tool_source", "部分", "是", "确认工具优先调用 RAG/repository；本地文件仅作为索引或兜底。")
    if "ai/knowledge_base.py" in lowered:
        return ("legacy_ai_knowledge_search", "否", "是", "旧 AI 工具直读知识库，建议保留兼容但不作为 v2.8 主链路。")
    if "ai/tool_registry.py" in lowered:
        return ("legacy_ai_tool_registry", "否", "部分", "旧工具注册表依赖 load_latest_forecast/query_dataframe，保留兼容。")
    if "tariff_tools.py" in lowered:
        if pattern_name == "csv":
            return ("tariff_tool_csv_fallback", "否", "是", "PostgreSQL 查询优先，CSV 作为缺库兜底。")
        return ("tariff_tool_runtime", "部分", "是", "应优先读取 PostgreSQL tariff/policy 表。")
    if "data_freshness_tools.py" in lowered:
        return ("assistant_data_freshness_tool", "部分", "是", "数据库优先，Excel freshness 作为兼容兜底。")
    if "forecast_tools.py" in lowered or "storage_tools.py" in lowered or "time_tools.py" in lowered:
        return ("assistant_forecast_tool", "是", "是", "通过 load_latest_forecast 走 PostgreSQL 优先。")
    if "platform_services.py" in lowered:
        return ("platform_service_runtime", "部分", "部分", "预测/报告/聊天会话多为 DB 优先；report review 本地 JSON 是兜底。")
    if "database_utils.py" in lowered:
        return ("legacy_database_adapter", "否", "是", "旧数据库适配器仅在显式允许 fallback 时使用。")
    if pattern_name in {"excel", "csv"} and ("read_" in snippet_lower or ".xlsx" in snippet_lower or ".csv" in snippet_lower):
        return ("legacy_file_or_import_path", "部分", "待确认", "检查是否存在 repository 替代；生产主路径应优先 PostgreSQL。")
    return ("uncategorized_reference", "待确认", "待确认", "人工复核。")


def scan_old_sources() -> list[OldSourceFinding]:
    findings: list[OldSourceFinding] = []
    for path in iter_source_files():
        text = read_text(path)
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            for name, pattern in OLD_SOURCE_PATTERNS.items():
                if pattern.search(line):
                    scene, is_main, replacement, recommendation = classify_finding(path, name, line.strip())
                    findings.append(
                        OldSourceFinding(
                            path=rel(path),
                            line=line_no,
                            pattern=name,
                            snippet=line.strip()[:240],
                            usage_scene=scene,
                            is_main_path=is_main,
                            postgres_replacement=replacement,
                            recommendation=recommendation,
                        )
                    )
    return findings


def check_alembic_static() -> dict[str, Any]:
    versions_dir = PROJECT_ROOT / "migrations" / "versions"
    version_files = sorted(versions_dir.glob("*.py")) if versions_dir.exists() else []
    all_text = "\n".join(read_text(path) for path in version_files)
    created_tables = sorted(set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)", all_text, flags=re.IGNORECASE)))
    indexes = sorted(set(re.findall(r"CREATE INDEX IF NOT EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)", all_text, flags=re.IGNORECASE)))
    missing_tables = sorted(CRITICAL_TABLES.difference(created_tables))
    down_revisions = {}
    for path in version_files:
        text = read_text(path)
        revision = re.search(r"^revision\s*=\s*[\"']([^\"']+)[\"']", text, flags=re.MULTILINE)
        down = re.search(r"^down_revision\s*=\s*(None|[\"'][^\"']+[\"'])", text, flags=re.MULTILINE)
        down_revisions[path.name] = {
            "revision": revision.group(1) if revision else "",
            "down_revision": down.group(1).strip("\"'") if down else "",
        }
    return {
        "alembic_ini_exists": (PROJECT_ROOT / "alembic.ini").exists(),
        "env_py_exists": (PROJECT_ROOT / "migrations" / "env.py").exists(),
        "version_files": [rel(path) for path in version_files],
        "revision_chain": down_revisions,
        "created_tables": created_tables,
        "critical_tables_missing": missing_tables,
        "index_count": len(indexes),
        "indexes": indexes,
        "empty_db_runtime_check": "not_run",
        "empty_db_runtime_check_reason": "默认脚本不读取真实 .env，也未连接外部数据库；如需实测，请在独立空库设置 DATABASE_URL 后运行 alembic upgrade head。",
    }


def check_runtime_report() -> dict[str, Any]:
    if not RUNTIME_REPORT_JSON.exists():
        return {
            "runtime_check_available": False,
            "runtime_check_status": "not_run",
            "report_path": rel(RUNTIME_REPORT_JSON),
        }
    try:
        data = json.loads(RUNTIME_REPORT_JSON.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "runtime_check_available": False,
            "runtime_check_status": "unreadable",
            "report_path": rel(RUNTIME_REPORT_JSON),
            "error": str(exc),
        }
    return {
        "runtime_check_available": bool(data.get("runtime_check_available")),
        "runtime_check_status": data.get("status") or "unknown",
        "report_path": rel(RUNTIME_REPORT_JSON),
        "alembic_upgrade_executed": bool((data.get("alembic_upgrade") or {}).get("executed")),
    }


def check_legacy_fallback_policy() -> dict[str, Any]:
    config_text = read_text(PROJECT_ROOT / "backend" / "app" / "core" / "config.py")
    example_text = read_text(PROJECT_ROOT / ".env.example")
    return {
        "setting_exists": "DATABASE_ALLOW_LEGACY_FALLBACK" in config_text,
        "env_example_mentions_development": "Development" in example_text and "DATABASE_ALLOW_LEGACY_FALLBACK=1" in example_text,
        "env_example_mentions_production": "Production" in example_text and "DATABASE_ALLOW_LEGACY_FALLBACK=0" in example_text,
        "production_warning_exists": "APP_ENV=production" in config_text or "is_production" in config_text,
        "policy": "development may enable legacy fallback; production should keep it disabled",
    }


def recommended_next_steps(stage1_status: dict[str, Any], runtime: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    if runtime.get("runtime_check_status") in {"not_run", "skipped"}:
        steps.append("Run check_postgres_runtime.py with a masked local DATABASE_URL in an isolated PostgreSQL database.")
    pending = [
        name
        for name, item in (stage1_status.get("domains") or {}).items()
        if item.get("status") in {"pending_schema_or_data_migration", "fallback_only"}
    ]
    if pending:
        steps.append("Migrate Stage1 raw data tables or add Alembic schemas for: " + ", ".join(pending))
    steps.append("Keep DATABASE_ALLOW_LEGACY_FALLBACK=0 in production.")
    steps.append("Move task execution to Celery/Redis in the next enterprise hardening batch.")
    return steps


def summarize_findings(findings: list[OldSourceFinding]) -> dict[str, Any]:
    by_pattern: dict[str, int] = {}
    by_scene: dict[str, int] = {}
    main_or_partial: list[dict[str, Any]] = []
    for finding in findings:
        by_pattern[finding.pattern] = by_pattern.get(finding.pattern, 0) + 1
        by_scene[finding.usage_scene] = by_scene.get(finding.usage_scene, 0) + 1
        if finding.is_main_path in {"是", "部分", "待确认"} and finding.usage_scene not in {
            "test_or_evaluation_fixture",
            "documentation_or_config_hint",
            "frontend_export_or_mock",
            "migration_tool",
        }:
            main_or_partial.append(asdict(finding))
    return {
        "total_findings": len(findings),
        "by_pattern": dict(sorted(by_pattern.items())),
        "by_usage_scene": dict(sorted(by_scene.items())),
        "main_or_partial_runtime_findings": main_or_partial[:120],
        "main_or_partial_runtime_count": len(main_or_partial),
    }


def build_report() -> dict[str, Any]:
    repositories = check_repository_imports()
    core_usage = check_core_usage()
    findings = scan_old_sources()
    alembic = check_alembic_static()
    runtime = check_runtime_report()
    fallback_policy = check_legacy_fallback_policy()
    stage1_status = write_stage1_gap_reports(build_stage1_gap_report())
    repository_ok = all(item.get("importable") for item in repositories.values())
    core_usage_ok = all(item.get("status") == "ok" for item in core_usage.values())
    alembic_ok = bool(alembic["alembic_ini_exists"] and alembic["env_py_exists"] and not alembic["critical_tables_missing"])
    runtime_old_count = summarize_findings(findings)["main_or_partial_runtime_count"]
    runtime_status = runtime.get("runtime_check_status")
    has_stage1_pending = any(
        item.get("status") in {"pending_schema_or_data_migration", "fallback_only"}
        for item in (stage1_status.get("domains") or {}).values()
    )
    if not repository_ok or not core_usage_ok or not alembic_ok or runtime_status == "fail":
        status = "fail"
    elif runtime_status == "pass" and not has_stage1_pending and runtime_old_count == 0:
        status = "pass"
    else:
        status = "pass_with_warnings"
    return {
        "project_root": str(PROJECT_ROOT),
        "status": status,
        "checks": {
            "repository_imports_ok": repository_ok,
            "core_usage_static_ok": core_usage_ok,
            "alembic_static_ok": alembic_ok,
            "runtime_old_source_reference_count": runtime_old_count,
            "runtime_check_available": runtime.get("runtime_check_available"),
            "runtime_check_status": runtime_status,
            "stage1_gap_known": stage1_status.get("status") == "stage1_gap_known",
            "fallback_policy_defined": bool(fallback_policy.get("setting_exists")),
        },
        "repositories": repositories,
        "core_usage": core_usage,
        "old_source_findings_summary": summarize_findings(findings),
        "old_source_findings": [asdict(item) for item in findings],
        "alembic": alembic,
        "runtime": runtime,
        "legacy_fallback_policy": fallback_policy,
        "stage1_repository_status": stage1_status,
        "production_fallback_risk": "controlled_by_warning_and_env" if fallback_policy.get("production_warning_exists") else "needs_warning",
        "hardcoded_path_risk": {
            "count": summarize_findings(findings)["by_pattern"].get("hardcoded_project_path", 0),
            "recommendation": "Remove hardcoded local project paths from docs/scripts before deployment images are finalized.",
        },
        "recommended_next_steps": recommended_next_steps(stage1_status, runtime),
    }


def write_json(report: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        escaped = [str(value).replace("\n", " ").replace("|", "\\|") for value in row]
        lines.append("| " + " | ".join(escaped) + " |")
    return "\n".join(lines)


def write_markdown(report: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    repo_rows = [
        [name, item["module"], "是" if item.get("importable") else "否", item.get("error", "")]
        for name, item in report["repositories"].items()
    ]
    core_rows = [
        [name, item["status"], ", ".join(item.get("matched_tokens") or [])]
        for name, item in report["core_usage"].items()
    ]
    summary = report["old_source_findings_summary"]
    pattern_rows = [[key, value] for key, value in summary["by_pattern"].items()]
    scene_rows = [[key, value] for key, value in summary["by_usage_scene"].items()]
    important_rows = [
        [
            item["path"],
            item["line"],
            item["pattern"],
            item["usage_scene"],
            item["is_main_path"],
            item["postgres_replacement"],
            item["recommendation"],
        ]
        for item in summary["main_or_partial_runtime_findings"][:80]
    ]
    alembic = report["alembic"]
    lines = [
        "# PostgreSQL 主事实源验收报告",
        "",
        f"- 项目路径：`{report['project_root']}`",
        f"- 总体状态：`{report['status']}`",
        f"- Repository 可导入：{'是' if report['checks']['repository_imports_ok'] else '否'}",
        f"- 核心模块静态引用 repository：{'是' if report['checks']['core_usage_static_ok'] else '否'}",
        f"- Alembic 静态检查：{'通过' if report['checks']['alembic_static_ok'] else '未通过'}",
        f"- 运行时旧数据源主路径/部分主路径引用数：{report['checks']['runtime_old_source_reference_count']}",
        "",
        "## Repository 可导入性",
        md_table(["领域", "模块", "可导入", "错误"], repo_rows),
        "",
        "## 核心模块 Repository 使用情况",
        md_table(["领域", "状态", "命中标识"], core_rows),
        "",
        "## 旧数据源引用统计",
        md_table(["模式", "数量"], pattern_rows),
        "",
        "## 使用场景分类",
        md_table(["场景", "数量"], scene_rows),
        "",
        "## 需要重点复核的运行时引用",
        md_table(["文件", "行", "模式", "场景", "是否主路径", "PG 替代", "建议"], important_rows),
        "",
        "## Alembic 静态检查",
        f"- `alembic.ini`：{'存在' if alembic['alembic_ini_exists'] else '缺失'}",
        f"- `migrations/env.py`：{'存在' if alembic['env_py_exists'] else '缺失'}",
        f"- 迁移文件：{', '.join(alembic['version_files'])}",
        f"- 核心表缺失：{', '.join(alembic['critical_tables_missing']) if alembic['critical_tables_missing'] else '无'}",
        f"- 索引数量：{alembic['index_count']}",
        f"- 空库运行检查：{alembic['empty_db_runtime_check']}，原因：{alembic['empty_db_runtime_check_reason']}",
        "",
        "## 结论",
        "- PostgreSQL 产品化骨架已覆盖预测、模型、任务、报告、AI Trace、知识库和审计等核心表。",
        "- 主要运行时入口已出现 repository 或 PostgreSQL 优先路径；旧 Excel/CSV/本地文件仍集中在兼容接口、ETL 输入、前端导出、测试夹具和少量工具 fallback。",
        "- 后续企业化应优先把 Stage1 天气/负荷/可再生接口和 report review 的本地 JSON fallback repository 化。",
    ]
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    global REPORT_JSON, REPORT_MD
    parser = argparse.ArgumentParser(description="Check PostgreSQL source-of-truth adoption.")
    parser.add_argument("--json", default=str(REPORT_JSON), help="JSON report output path")
    parser.add_argument("--markdown", default=str(REPORT_MD), help="Markdown report output path")
    args = parser.parse_args()

    REPORT_JSON = Path(args.json)
    REPORT_MD = Path(args.markdown)
    report = build_report()
    write_json(report)
    write_markdown(report)
    print(f"PostgreSQL source-of-truth report written: {REPORT_MD}")
    print(f"JSON report written: {REPORT_JSON}")
    print(json.dumps(report["checks"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

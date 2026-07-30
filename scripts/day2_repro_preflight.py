from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import get_settings  # noqa: E402


MIGRATIONS = ROOT / "migrations" / "versions"
REQUIRED_PRODUCTION_VALUES = {
    "APP_ENV": "production",
    "AUTH_REQUIRED": "1",
    "ADMIN_INITIALIZED": "1",
    "DATABASE_ALLOW_LEGACY_FALLBACK": "0",
    "TASK_EXECUTION_MODE": "celery",
    "VITE_AUTH_REQUIRED": "1",
    "RAG_EMBEDDING_ALLOW_FALLBACK": "0",
    "RAG_FILE_FALLBACK_ENABLED": "0",
}
SECRET_KEYS = {
    "JWT_SECRET_KEY",
    "POSTGRES_PASSWORD",
    "ADMIN_PASSWORD",
    "DEEPSEEK_API_KEY",
    "LLM_API_KEY",
    "LOCAL_LLM_API_KEY",
}
OBVIOUS_PLACEHOLDER_MARKERS = ("replace_with", "generate_", "<", "${")
FORBIDDEN_WEAK_VALUES = {"change_me", "changeme", "password", "postgres", "secret"}


def _run(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip()[:1000],
            "stderr": completed.stderr.strip()[:1000],
        }
    except Exception as exc:
        return {"command": command, "returncode": -1, "error": f"{type(exc).__name__}: {exc}"}


def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", value)
    if not match:
        return ()
    return tuple(int(part) for part in match.groups(default="0"))


def _runtime_checks() -> tuple[dict[str, Any], list[str]]:
    npm = "npm.cmd" if os.name == "nt" else "npm"
    checks = {
        "python": {"version": sys.version.split()[0], "executable": sys.executable},
        "node": _run(["node", "--version"]),
        "npm": _run([npm, "--version"]),
        "docker": _run(["docker", "--version"]),
        "docker_compose": _run(["docker", "compose", "version"]),
        "alembic_heads": _run([sys.executable, "-m", "alembic", "heads"]),
    }
    failures: list[str] = []
    if sys.version_info[:2] != (3, 11):
        failures.append("Python 必须为 3.11.x")
    node_version = _version_tuple(str(checks["node"].get("stdout", "")))
    if not node_version or not ((18, 0, 0) <= node_version < (25, 0, 0)):
        failures.append("Node 必须满足 >=18 <25")
    npm_version = _version_tuple(str(checks["npm"].get("stdout", "")))
    if not npm_version or not ((9, 0, 0) <= npm_version < (12, 0, 0)):
        failures.append("npm 必须满足 >=9 <12")
    for name in ("docker", "docker_compose", "alembic_heads"):
        if checks[name].get("returncode") != 0:
            failures.append(f"{name} 不可用")
    if "0016_strategy_runtime (head)" not in str(checks["alembic_heads"].get("stdout", "")):
        failures.append("Alembic 必须只有 0016_strategy_runtime head")
    return checks, failures


def _config_checks(path: Path) -> tuple[dict[str, Any], list[str]]:
    values = _parse_env(path)
    failures: list[str] = []
    for key, expected in REQUIRED_PRODUCTION_VALUES.items():
        if values.get(key) != expected:
            failures.append(f"{key} 必须为 {expected}")
    for key in ("JWT_SECRET_KEY", "POSTGRES_PASSWORD"):
        value = values.get(key, "")
        if not value:
            failures.append(f"{key} 缺失")
        elif value.lower() in FORBIDDEN_WEAK_VALUES:
            failures.append(f"{key} 使用禁止的弱默认值")
        elif not any(marker in value.lower() for marker in OBVIOUS_PLACEHOLDER_MARKERS):
            failures.append(f"{key} 示例值必须是明显占位值")
    for key in ("DEEPSEEK_API_KEY", "LLM_API_KEY"):
        if values.get(key, ""):
            failures.append(f"{key} 示例中必须为空")
    return {
        "path": str(path),
        "keys": sorted(values),
        "secret_keys_present": {key: key in values for key in sorted(SECRET_KEYS)},
        "secret_values_redacted": True,
    }, failures


def _migration_checks() -> tuple[dict[str, Any], list[str]]:
    records: list[dict[str, Any]] = []
    failures: list[str] = []
    for path in sorted(MIGRATIONS.glob("*.py")):
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
        function_names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        record = {
            "file": path.name,
            "has_upgrade": "upgrade" in function_names,
            "has_downgrade": "downgrade" in function_names,
            "public_qualified": bool(re.search(r"(?i)\bpublic\s*\.", source)),
            "drop_database": bool(re.search(r"(?i)\bdrop\s+database\b", source)),
            "system_catalog_write": bool(
                re.search(
                    r"(?i)\b(?:insert\s+into|update|delete\s+from|alter\s+table|drop\s+table)"
                    r"\s+(?:pg_catalog\.|information_schema\.)",
                    source,
                )
            ),
            "direct_alembic_version": bool(re.search(r"(?i)\balembic_version\b", source)),
        }
        records.append(record)
        if not record["has_upgrade"] or not record["has_downgrade"]:
            failures.append(f"{path.name} 缺少 upgrade/downgrade")
        for key in ("public_qualified", "drop_database", "system_catalog_write", "direct_alembic_version"):
            if record[key]:
                failures.append(f"{path.name} 触发迁移静态禁项 {key}")
    return {"files_scanned": len(records), "records": records}, failures


def _port_checks() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for port in (5432, 6379, 8000, 5173, 8080, 18000, 15173):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.3)
            result[str(port)] = "listening" if sock.connect_ex(("127.0.0.1", port)) == 0 else "free"
    return result


def _database_check() -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    settings = get_settings()
    parsed = make_url(settings.database_url)
    configured = {
        "host": parsed.host,
        "port": parsed.port or 5432,
        "database": parsed.database,
        "user": parsed.username,
        "password_redacted": True,
    }
    if configured["host"] not in {"localhost", "127.0.0.1", "::1"}:
        failures.append("数据库 host 不是 localhost")
    if configured["port"] != 5432 or configured["database"] != "postgres":
        failures.append("数据库目标不是 localhost:5432/postgres")
    engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    with engine.connect() as connection:
        identity = dict(
            connection.execute(
                text(
                    "SELECT current_database() AS database, current_user AS current_user, "
                    "inet_server_port() AS server_port, current_setting('server_version') AS server_version"
                )
            ).mappings().one()
        )
        versions = connection.execute(
            text("SELECT version_num FROM public.alembic_version ORDER BY version_num")
        ).scalars().all()
    if identity["database"] != "postgres" or int(identity["server_port"]) != 5432:
        failures.append("数据库实际身份不符合门禁")
    if versions != ["0016_strategy_runtime"]:
        failures.append("活动 Alembic 版本不是 0016_strategy_runtime")
    return {"configured": configured, "identity": identity, "active_alembic_version": versions}, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Day 2 可复现环境只读前置检查")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.docker.example")
    parser.add_argument("--check-db", action="store_true")
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    runtime, runtime_failures = _runtime_checks()
    config, config_failures = _config_checks(args.env_file.resolve())
    migrations, migration_failures = _migration_checks()
    failures.extend(runtime_failures)
    failures.extend(config_failures)
    failures.extend(migration_failures)
    database: dict[str, Any] | None = None
    if args.check_db:
        database, database_failures = _database_check()
        failures.extend(database_failures)
    git_status = _run(["git", "status", "--short"])
    if args.require_clean and git_status.get("stdout"):
        failures.append("Git 工作树不干净")
    result = {
        "ok": not failures,
        "failures": failures,
        "runtime": runtime,
        "config": config,
        "migrations": migrations,
        "ports": _port_checks(),
        "database": database,
        "git_status": git_status,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

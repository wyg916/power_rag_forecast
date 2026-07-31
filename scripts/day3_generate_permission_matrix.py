from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from starlette.routing import compile_path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.api_security import MATRIX_PATH, PUBLIC_ROUTE_KEYS, load_route_policies
from backend.app.core.security import ROLE_PERMISSIONS, get_current_user
from backend.app.main import app


MD_PATH = MATRIX_PATH.with_suffix(".md")
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
FIELDS = [
    "Method",
    "Path",
    "Module",
    "Handler",
    "Route Name",
    "Response Model",
    "Risk Level",
    "Current Guard",
    "Target Guard",
    "Required Permission",
    "Allowed Roles",
    "Anonymous",
    "Write Operation",
    "Frontend Consumer",
    "Notes",
]
ROLE_ORDER = ("admin", "analyst", "viewer", "reviewer", "developer")


def _walk_routes(routes: Iterable[Any]) -> Iterable[Any]:
    for route in routes:
        candidates = getattr(route, "_effective_candidates", None)
        if candidates is not None:
            yield from _walk_routes(candidates)
        elif getattr(route, "path", None):
            yield route


def route_records() -> list[dict[str, Any]]:
    app.openapi()
    records: list[dict[str, Any]] = []
    for route in _walk_routes(app.router.routes):
        endpoint = getattr(route, "endpoint", None)
        for method in sorted(set(getattr(route, "methods", set())) & HTTP_METHODS):
            records.append(
                {
                    "method": method,
                    "path": route.path,
                    "module": getattr(endpoint, "__module__", route.__class__.__module__),
                    "handler": getattr(endpoint, "__name__", getattr(route, "name", "unknown")),
                    "route_name": getattr(route, "name", ""),
                    "response_model": str(getattr(route, "response_model", "")),
                    "include_in_schema": bool(getattr(route, "include_in_schema", False)),
                    "is_sse": bool(getattr(route, "is_sse_stream", False)) or route.path == "/api/ai/chat/stream",
                    "current_guard": _current_guard(route),
                }
            )
    return sorted(records, key=lambda row: (row["path"], row["method"]))


def _dependency_labels(dependant: Any) -> set[str]:
    labels: set[str] = set()
    for child in getattr(dependant, "dependencies", ()) or ():
        call = getattr(child, "call", None)
        if call is get_current_user:
            labels.add("auth:get_current_user")
        elif call is not None:
            closure = getattr(call, "__closure__", None) or ()
            values = [cell.cell_contents for cell in closure if isinstance(cell.cell_contents, str)]
            if values:
                labels.add(f"permission:{values[0]}")
            else:
                labels.add(f"dependency:{getattr(call, '__name__', call.__class__.__name__)}")
        labels.update(_dependency_labels(child))
    return labels


def _current_guard(route: Any) -> str:
    labels = _dependency_labels(getattr(route, "dependant", None))
    return "|".join(sorted(labels)) if labels else "none"


def required_permission(method: str, path: str) -> str:
    key = (method, path)
    if key in PUBLIC_ROUTE_KEYS:
        return ""
    if path.startswith("/api/auth/"):
        return "auth:self"
    if path in {"/api/security/me"}:
        return "auth:self"
    if path == "/api/security/permissions":
        return "security:read"
    if path.startswith("/api/audit/") or path == "/api/settings/audit-logs":
        return "audit:read"
    if path.startswith("/api/users") or path.startswith("/api/settings/users"):
        return "user:read" if method == "GET" else "user:write"
    if path == "/api/settings/roles/permissions":
        return "user:read" if method == "GET" else "user:write"
    if path == "/api/db/health":
        return "system:diagnostics"
    if path.startswith("/api/settings/"):
        return "settings:read" if method == "GET" else "settings:write"
    if path == "/api/ai/local-model/status":
        return "model:read"
    if path == "/api/business-summary" or path.startswith("/api/dashboard/"):
        return "dashboard:read"
    if path.startswith(("/api/forecast/", "/api/prediction/", "/api/risk/", "/api/load/", "/api/weather/", "/api/renewable/", "/api/market/", "/api/source/")):
        return "forecast:run" if method != "GET" else "forecast:read"
    if path.startswith("/api/data/"):
        if path == "/api/data/sql/query":
            return "data:query"
        if path in {"/api/data/refresh", "/api/data/sync-core"}:
            return "data:sync"
        if path.endswith("/export"):
            return "data:export"
        return "data:read"
    if path.startswith("/api/reports"):
        if path.endswith("/download"):
            return "report:download"
        if path.endswith("/reviews") or path.endswith(("/approve", "/reject", "/publish")):
            return "report:review"
        if method != "GET":
            return "report:generate"
        return "report:read"
    if path.startswith(("/api/strategy", "/api/strategies", "/api/anomaly")):
        if path.endswith("/reviews") or path.endswith(("/approve", "/reject", "/return")) or path == "/api/strategy/reviews":
            return "strategy:review"
        if path.endswith("/publish"):
            return "strategy:publish"
        if path.endswith("/submit"):
            return "strategy:submit"
        if "generate" in path or path == "/api/anomaly/explain":
            return "strategy:generate"
        if path == "/api/strategy/config" and method != "GET":
            return "strategy:manage"
        if path == "/api/strategies/{strategy_id}/{action}":
            return "strategy:manage"
        return "strategy:read"
    if path.startswith("/api/knowledge/"):
        if path.endswith("/export"):
            return "knowledge:export"
        if path.endswith(("/batch-validate", "/embedding-refresh", "/index-local", "/upload")):
            return "knowledge:write"
        return "knowledge:read"
    if path.startswith(("/api/models/", "/api/model/")):
        if path.endswith("/export"):
            return "model:export"
        return "model:manage" if method != "GET" else "model:read"
    if path.startswith(("/api/tasks", "/api/task/", "/api/scheduled-tasks")):
        if method != "GET":
            return "task:manage"
        if any(part in path for part in ("/logs", "/health", "/queues/", "/retry/")):
            return "task:diagnostics"
        return "task:read"
    if path.startswith("/api/ai/traces"):
        return "trace:read"
    if path == "/api/ai/chat/sessions/export":
        return "assistant:export"
    if path.startswith("/api/ai/"):
        return "assistant:use"
    if path == "/api/model-gateway/health":
        return "model:read"
    if path == "/api/model-gateway/chat/completions":
        return "assistant:use"
    raise ValueError(f"Unclassified route: {method} {path}")


def _allowed_roles(permission: str) -> str:
    if not permission:
        return "anonymous"
    allowed = [
        role
        for role in ROLE_ORDER
        if "*" in ROLE_PERMISSIONS[role] or permission in ROLE_PERMISSIONS[role]
    ]
    return "|".join(allowed)


def _risk(permission: str, anonymous: bool, write: bool) -> str:
    if anonymous:
        return "public"
    allowed = set(_allowed_roles(permission).split("|"))
    if write and allowed == {"admin"}:
        return "admin"
    sensitive = {
        "assistant:export",
        "audit:read",
        "data:export",
        "data:query",
        "model:export",
        "model:manage",
        "model:read",
        "report:download",
        "report:review",
        "security:read",
        "settings:read",
        "settings:write",
        "strategy:manage",
        "strategy:publish",
        "strategy:review",
        "system:diagnostics",
        "task:diagnostics",
        "task:manage",
        "trace:read",
        "user:read",
        "user:write",
    }
    return "sensitive" if permission in sensitive else "business"


def _frontend_consumers(records: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    compiled = [(row["method"], row["path"], compile_path(row["path"])[0]) for row in records]
    consumers: dict[tuple[str, str], set[str]] = defaultdict(set)
    token_pattern = re.compile(r"""(?P<quote>["'`])(?P<value>/(?:api/[^"'`\s]+|health))(?P=quote)""")
    for source in sorted((ROOT / "frontend" / "src").rglob("*")):
        if source.suffix not in {".ts", ".tsx"}:
            continue
        for line_no, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            for match in token_pattern.finditer(line):
                value = match.group("value").split("?", 1)[0]
                value = re.sub(r"\$\{[^}]+\}", "sample", value)
                for method, path, regex in compiled:
                    if regex.fullmatch(value):
                        consumers[(method, path)].add(f"{source.relative_to(ROOT).as_posix()}:{line_no}")
    return {key: ";".join(sorted(values)) for key, values in consumers.items()}


def build_rows() -> list[dict[str, str]]:
    records = route_records()
    consumers = _frontend_consumers(records)
    path_methods: dict[str, set[str]] = defaultdict(set)
    handler_paths: dict[tuple[str, str], set[str]] = defaultdict(set)
    for record in records:
        path_methods[record["path"]].add(record["method"])
        handler_paths[(record["module"], record["handler"])].add(record["path"])

    rows: list[dict[str, str]] = []
    for record in records:
        method, path = record["method"], record["path"]
        permission = required_permission(method, path)
        anonymous = (method, path) in PUBLIC_ROUTE_KEYS
        write = method != "GET"
        notes: list[str] = []
        if len(path_methods[path]) > 1:
            notes.append("same-path methods=" + "|".join(sorted(path_methods[path])))
        aliases = sorted(handler_paths[(record["module"], record["handler"])] - {path})
        if aliases:
            notes.append("compatibility alias of " + "|".join(aliases))
        if record["is_sse"]:
            notes.append("SSE stream")
        if path.endswith("/download") or path.endswith("/export"):
            notes.append("download/export response")
        rows.append(
            {
                "Method": method,
                "Path": path,
                "Module": record["module"],
                "Handler": record["handler"],
                "Route Name": record["route_name"],
                "Response Model": record["response_model"],
                "Risk Level": _risk(permission, anonymous, write),
                "Current Guard": record["current_guard"],
                "Target Guard": "explicit-public-whitelist" if anonymous else f"authenticated+permission:{permission}",
                "Required Permission": permission,
                "Allowed Roles": _allowed_roles(permission),
                "Anonymous": "yes" if anonymous else "no",
                "Write Operation": "yes" if write else "no",
                "Frontend Consumer": consumers.get((method, path), "none"),
                "Notes": "; ".join(notes) or "none",
            }
        )
    return rows


def write_outputs(rows: list[dict[str, str]]) -> None:
    MATRIX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MATRIX_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    counts = Counter(row["Risk Level"] for row in rows)
    lines = [
        "# Day 3 API 权限矩阵",
        "",
        f"- 方法+路径总数：{len(rows)}",
        f"- 唯一路径数：{len({row['Path'] for row in rows})}",
        f"- 风险分布：{dict(sorted(counts.items()))}",
        f"- 公共白名单：{sum(row['Anonymous'] == 'yes' for row in rows)}",
        "- 规范：CSV 为机器可读事实源；本文件由脚本同步生成。",
        "",
        "| " + " | ".join(FIELDS) + " |",
        "|" + "|".join("---" for _ in FIELDS) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row[field].replace("|", "\\|") for field in FIELDS) + " |")
    MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the Day 3 API permission matrix.")
    parser.add_argument("--check", action="store_true", help="Fail if generated rows differ from the committed CSV.")
    args = parser.parse_args()
    rows = build_rows()
    if args.check:
        with MATRIX_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
            current = list(csv.DictReader(handle))
        if current != rows:
            raise SystemExit("API permission matrix is stale; run this script without --check")
    else:
        write_outputs(rows)
        load_route_policies.cache_clear()
    print(
        json.dumps(
            {
                "route_method_count": len(rows),
                "unique_path_count": len({row["Path"] for row in rows}),
                "public_count": sum(row["Anonymous"] == "yes" for row in rows),
                "protected_count": sum(row["Anonymous"] == "no" for row in rows),
                "method_distribution": dict(sorted(Counter(row["Method"] for row in rows).items())),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

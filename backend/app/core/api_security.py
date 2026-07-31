from __future__ import annotations

import csv
import inspect
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.routing import compile_path

from .redaction import mask_secret_fields
from .security import CurrentUser, get_current_user


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = PROJECT_ROOT / "docs" / "codex" / "security" / "API_PERMISSION_MATRIX.csv"
PUBLIC_ROUTE_KEYS = {
    ("POST", "/api/auth/login"),
    ("GET", "/api/health"),
    ("GET", "/health"),
    ("GET", "/openapi.json"),
    ("GET", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("GET", "/redoc"),
}
DEVELOPMENT_DOC_ROUTE_KEYS = {
    ("GET", "/openapi.json"),
    ("GET", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("GET", "/redoc"),
}


@dataclass(frozen=True)
class RoutePolicy:
    method: str
    path: str
    risk_level: str
    permission: str
    anonymous: bool
    write_operation: bool
    allowed_roles: tuple[str, ...]
    path_regex: object

    def matches(self, method: str, path: str) -> bool:
        return self.method == method and bool(self.path_regex.match(path))


def _bool(value: str) -> bool:
    return value.strip().lower() == "yes"


@lru_cache(maxsize=1)
def load_route_policies() -> tuple[RoutePolicy, ...]:
    if not MATRIX_PATH.is_file():
        raise RuntimeError(f"API security matrix is missing: {MATRIX_PATH}")
    with MATRIX_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "Method",
        "Path",
        "Risk Level",
        "Required Permission",
        "Allowed Roles",
        "Anonymous",
        "Write Operation",
    }
    if not rows or not required.issubset(rows[0]):
        raise RuntimeError("API security matrix is empty or has invalid columns")

    policies: list[RoutePolicy] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        method = row["Method"].strip().upper()
        path = row["Path"].strip()
        key = (method, path)
        if key in seen:
            raise RuntimeError(f"Duplicate API security matrix route: {method} {path}")
        seen.add(key)
        anonymous = _bool(row["Anonymous"])
        permission = row["Required Permission"].strip()
        if anonymous != (key in PUBLIC_ROUTE_KEYS):
            raise RuntimeError(f"Public whitelist mismatch: {method} {path}")
        if not anonymous and not permission:
            raise RuntimeError(f"Protected route has no permission: {method} {path}")
        regex, _, _ = compile_path(path)
        policies.append(
            RoutePolicy(
                method=method,
                path=path,
                risk_level=row["Risk Level"].strip(),
                permission=permission,
                anonymous=anonymous,
                write_operation=_bool(row["Write Operation"]),
                allowed_roles=tuple(filter(None, row["Allowed Roles"].split("|"))),
                path_regex=regex,
            )
        )
    return tuple(policies)


def policy_for_request(method: str, path: str) -> RoutePolicy | None:
    normalized_method = method.upper()
    for policy in load_route_policies():
        if policy.matches(normalized_method, path):
            return policy
    return None


def _walk_routes(routes: Iterable[Any]) -> Iterable[Any]:
    for route in routes:
        candidates = getattr(route, "_effective_candidates", None)
        if candidates is not None:
            yield from _walk_routes(candidates)
        elif getattr(route, "path", None):
            yield route


def app_route_keys(app: Any) -> set[tuple[str, str]]:
    app.openapi()
    keys: set[tuple[str, str]] = set()
    for route in _walk_routes(app.router.routes):
        for method in set(getattr(route, "methods", set())) & {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            keys.add((method, route.path))
    return keys


def validate_app_route_coverage(app: Any) -> None:
    actual = app_route_keys(app)
    classified = {(policy.method, policy.path) for policy in load_route_policies()}
    missing = sorted(actual - classified)
    allowed_extras = DEVELOPMENT_DOC_ROUTE_KEYS - actual
    stale = sorted(classified - actual - allowed_extras)
    if missing or stale:
        raise RuntimeError(f"API security matrix coverage mismatch: missing={missing}, stale={stale}")


async def _resolve_current_user(request: Request) -> CurrentUser:
    override = request.app.dependency_overrides.get(get_current_user)
    resolver: Callable[..., CurrentUser | Awaitable[CurrentUser]] = override or get_current_user
    parameters = inspect.signature(resolver).parameters
    result = resolver(request) if parameters else resolver()
    if inspect.isawaitable(result):
        result = await result
    return result


def _error_response(exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": mask_secret_fields(exc.detail)},
        headers=exc.headers,
    )


class ApiSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.method.upper() == "OPTIONS":
            return await call_next(request)

        policy = policy_for_request(request.method, request.url.path)
        if policy is None:
            return await call_next(request)
        if policy.anonymous:
            return await call_next(request)

        try:
            user = await _resolve_current_user(request)
            if not user.has_permission(policy.permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"缺少权限：{policy.permission}",
                )
        except HTTPException as exc:
            return _error_response(exc)

        request.state.current_user = user
        return await call_next(request)

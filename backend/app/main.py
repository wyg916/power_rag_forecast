from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.model_gateway.router import router as model_gateway_router

from .api.v1.router import api_router
from .config import APP_VERSION, PLATFORM_NAME
from .core.config import get_settings
from .core.api_security import ApiSecurityMiddleware, validate_app_route_coverage
from .core.redaction import mask_secret_fields
from .data_registry import validate_dataset_registry
from .db.session import get_engine, get_security_engine, validate_runtime_database_roles
from .observability import configure_app_logging
from .services.dataset_query_service import validate_registry_against_database
from .services.rag_runtime_warmup import prewarm_enterprise_rag_runtime


def _cors_allowed_origins() -> list[str]:
    configured = os.getenv("CORS_ALLOWED_ORIGINS") or os.getenv("WEB_CORS_ALLOWED_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]

    frontend_port = os.getenv("WEB_FRONTEND_PORT", "5173").strip() or "5173"
    dev_ports = ["5173", "5174", frontend_port]
    origins: list[str] = []
    for port in dict.fromkeys(dev_ports):
        origins.extend([f"http://localhost:{port}", f"http://127.0.0.1:{port}"])
    return origins


async def sanitized_http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": mask_secret_fields(exc.detail)},
        headers=exc.headers,
    )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_app_logging()
    docs_enabled = not settings.is_production
    app = FastAPI(
        title=PLATFORM_NAME,
        version=APP_VERSION,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.add_exception_handler(StarletteHTTPException, sanitized_http_exception_handler)
    app.add_middleware(ApiSecurityMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(model_gateway_router)
    app.include_router(api_router)

    @app.on_event("startup")
    async def validate_api_security_matrix() -> None:
        validate_app_route_coverage(app)
        validate_dataset_registry()
        if settings.has_database_url and not settings.is_test:
            runtime_engine = get_engine()
            validate_runtime_database_roles(runtime_engine, get_security_engine())
            validate_registry_against_database(runtime_engine)
        prewarm_enterprise_rag_runtime()

    return app


app = create_app()

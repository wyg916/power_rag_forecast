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
from .core.redaction import mask_secret_fields
from .observability import configure_app_logging


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
    get_settings()
    configure_app_logging()
    app = FastAPI(title=PLATFORM_NAME, version=APP_VERSION)
    app.add_exception_handler(StarletteHTTPException, sanitized_http_exception_handler)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(model_gateway_router)
    app.include_router(api_router)
    return app


app = create_app()

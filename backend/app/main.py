from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.model_gateway.router import router as model_gateway_router

from .api.v1.router import api_router
from .config import APP_VERSION, PLATFORM_NAME
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


def create_app() -> FastAPI:
    configure_app_logging()
    app = FastAPI(title=PLATFORM_NAME, version=APP_VERSION)
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

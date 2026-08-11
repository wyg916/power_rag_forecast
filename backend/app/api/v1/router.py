from __future__ import annotations

from fastapi import APIRouter

from .endpoints import assistant, auth, chatbi, dashboard, data, forecast, knowledge, model, report, strategy, system, task, users


api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(system.router)
api_router.include_router(data.router)
api_router.include_router(dashboard.router)
api_router.include_router(forecast.router)
api_router.include_router(strategy.router)
api_router.include_router(assistant.router)
api_router.include_router(chatbi.router)
api_router.include_router(knowledge.router)
api_router.include_router(report.router)
api_router.include_router(model.router)
api_router.include_router(task.router)
api_router.include_router(users.router)

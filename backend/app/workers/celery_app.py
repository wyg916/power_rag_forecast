from __future__ import annotations

from backend.app.core.config import get_settings

try:
    from celery import Celery
except Exception:  # pragma: no cover - optional runtime dependency
    Celery = None  # type: ignore


def create_celery_app():
    if Celery is None:
        return None
    settings = get_settings()
    app = Celery("power_trading_platform", broker=settings.celery_broker_url, backend=settings.celery_result_backend)
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="Asia/Shanghai",
        enable_utc=False,
        task_track_started=True,
        broker_connection_retry_on_startup=True,
        include=["backend.app.workers.tasks"],
    )
    return app


celery_app = create_celery_app()

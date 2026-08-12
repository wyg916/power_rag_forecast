from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from backend.app.ai_assistant.tools import execute_tool
from backend.app.core.config import reset_settings_cache
from backend.app.db.session import get_engine, reset_db_cache
from backend.app.main import app
from backend.app.repositories.knowledge_repository import ensure_seed_knowledge
from backend.app.source_contract import SourceType, source_meta


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DB = "intelligent_ops_t005_source_contract_test"


def _reset_runtime():
    reset_settings_cache()
    reset_db_cache()
    return get_engine()


@pytest.fixture(autouse=True)
def _cleanup_t005_runs():
    """Keep this contract test order-independent inside the shared disposable Schema."""

    yield
    if os.environ.get("BETA10D_TEST_ISOLATION_ACTIVE") != "1":
        return
    engine = _reset_runtime()
    if engine is None:
        return
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM forecast_results WHERE run_id LIKE 't005_%'"))
        connection.execute(text("DELETE FROM forecast_runs WHERE run_id LIKE 't005_%'"))


def _insert_run(engine, *, status: str, finished_at: datetime, include_results: bool) -> str:
    run_id = f"t005_{status}_{uuid4().hex[:12]}"
    forecast_start = (finished_at + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    forecast_end = forecast_start + timedelta(hours=23)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO forecast_runs (
                    run_id, status, domain, target_name,
                    forecast_start_at, forecast_end_at,
                    model_id, model_version, feature_version, schema_hash,
                    result_hash, source_type, generated_at, created_at, updated_at,
                    started_at, finished_at, record_count, row_count
                )
                VALUES (
                    :run_id, :status, 'price', 'da_price',
                    :forecast_start, :forecast_end,
                    't005-model-id', 't005-model-v1', 't005-features-v1', 't005-schema-hash',
                    :result_hash, 'real', :finished_at, :finished_at, :finished_at,
                    :finished_at, :finished_at, :record_count, :record_count
                )
                """
            ),
            {
                "run_id": run_id,
                "status": status,
                "forecast_start": forecast_start,
                "forecast_end": forecast_end,
                "finished_at": finished_at,
                "record_count": 24 if include_results else 0,
                "result_hash": uuid4().hex if include_results else None,
            },
        )
        if include_results:
            for index in range(24):
                forecast_time = forecast_start + timedelta(hours=index)
                conn.execute(
                    text(
                        """
                        INSERT INTO forecast_results (
                            run_id, forecast_datetime, forecast_time,
                            predicted_price, corrected_predicted_price,
                            risk_level, spike_risk_prob, source_row,
                            model_version, feature_version, generated_at, source_type
                        )
                        VALUES (
                            :run_id, :forecast_time, :forecast_time,
                            :price, :price, :risk_level, :risk_probability, :source_row,
                            't005-model-v1', 't005-features-v1', :generated_at, 'real'
                        )
                        """
                    ),
                    {
                        "run_id": run_id,
                        "forecast_time": forecast_time,
                        "price": 80.0 + index,
                        "risk_level": "high" if index >= 20 else "low",
                        "risk_probability": 0.7 if index >= 20 else 0.1,
                        "source_row": index + 1,
                        "generated_at": finished_at,
                    },
                )
    return run_id


def _table_snapshot(engine) -> dict[str, tuple[int, str]]:
    candidates = [
        "forecast_runs",
        "forecast_results",
        "model_registry",
        "model_versions",
        "report_runs",
        "strategy_advice",
        "anomaly_explanations",
        "audit_logs",
        "ai_chat_sessions",
        "ai_chat_messages",
        "kb_documents",
        "kb_chunks",
    ]
    existing = set(inspect(engine).get_table_names())
    snapshot: dict[str, tuple[int, str]] = {}
    with engine.connect() as conn:
        for table in candidates:
            if table not in existing:
                continue
            row = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*) AS rows_count,
                           MD5(COALESCE(STRING_AGG(ROW_TO_JSON(t)::text, '|' ORDER BY ROW_TO_JSON(t)::text), '')) AS content_hash
                    FROM "{table}" AS t
                    """
                )
            ).mappings().one()
            snapshot[table] = (int(row["rows_count"]), str(row["content_hash"]))
    return snapshot


def test_source_type_enum_and_timezone_contract():
    assert {item.value for item in SourceType} == {
        "real",
        "historical",
        "simulated",
        "demo",
        "seed",
        "fallback",
        "derived",
        "ai_inferred",
        "unavailable",
    }
    for source_type in SourceType:
        meta = source_meta(source_type, "electricity_day_ahead_price", generated_at="2026-07-16 12:00:00")
        assert meta["source_type"] == source_type.value
        assert meta["generated_at"].endswith("Z")
        assert isinstance(meta["evidence"], list)


@pytest.mark.integration
def test_api_web_ai_share_run_and_all_read_paths_are_side_effect_free(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AUTH_REQUIRED", "0")
    monkeypatch.setenv("DATABASE_ALLOW_LEGACY_FALLBACK", "0")
    engine = _reset_runtime()
    if os.environ.get("BETA10D_TEST_ISOLATION_ACTIVE") == "1":
        assert engine.url.database == "postgres"
        expected_prefix = os.environ.get("BETA10D_TEST_SCHEMA_PREFIX", "beta10d_day3_close_")
        with engine.connect() as connection:
            assert str(connection.exec_driver_sql("SELECT current_schema()").scalar_one()).startswith(expected_prefix)
    else:
        assert engine.url.database == EXPECTED_DB
    assert ensure_seed_knowledge(explicit=True).get("available") is True
    assert ensure_seed_knowledge().get("blocked") is True

    historical_run = _insert_run(
        engine,
        status="success",
        finished_at=datetime.now(timezone.utc) - timedelta(days=2),
        include_results=True,
    )
    failed_run = _insert_run(
        engine,
        status="failed",
        finished_at=datetime.now(timezone.utc) - timedelta(hours=1),
        include_results=False,
    )
    latest_run = _insert_run(
        engine,
        status="success",
        finished_at=datetime.now(timezone.utc),
        include_results=True,
    )

    client = TestClient(app)
    latest = client.get("/api/forecast/runs/latest-success").json()
    context = client.get("/api/source/context").json()
    forecast = client.get("/api/forecast/latest").json()
    dashboard = client.get("/api/dashboard/summary").json()
    ai_latest = execute_tool("get_forecast_metrics", run_id="latest")
    ai_historical = execute_tool("get_forecast_metrics", run_id=historical_run)

    assert latest["run"]["run_id"] == latest_run
    assert context["meta"]["run_id"] == latest_run
    assert forecast["meta"]["run_id"] == latest_run
    assert dashboard["meta"]["run_id"] == latest_run
    assert ai_latest["meta"]["run_id"] == latest_run
    assert ai_latest["meta"]["source_type"] == "derived"
    assert ai_historical["meta"]["run_id"] == historical_run
    assert ai_historical["meta"]["is_stale"] is True
    assert ai_historical["meta"]["stale_reason"] == "historical_run"

    historical = client.get(f"/api/forecast/runs/{historical_run}").json()
    failed = client.get(f"/api/forecast/runs/{failed_run}").json()
    unavailable = client.get("/api/source/context?run_id=missing-t005-run").json()
    wrong_domain = client.get("/api/source/context?domain=load_forecast")
    unknown_domain = client.get("/api/source/context?domain=unknown")
    knowledge = client.get("/api/knowledge/documents").json()
    assert historical["meta"]["source_type"] == "historical"
    assert failed["meta"]["source_type"] == "unavailable"
    assert failed["meta"]["unavailable_reason"] == "run_not_successful"
    assert unavailable["meta"]["source_type"] == "unavailable"
    assert unavailable["data"] is None
    assert wrong_domain.json()["meta"]["unavailable_reason"] == "domain_not_supported_by_forecast_results"
    assert unknown_domain.status_code == 400
    assert all(item.get("source_type") != "seed" for item in knowledge.get("items") or [])

    before = _table_snapshot(engine)
    paths = [
        "/api/forecast/runs/latest-success",
        f"/api/forecast/runs/{latest_run}",
        "/api/models/metrics",
        "/api/models/active",
        "/api/dashboard/summary",
        "/api/knowledge/documents",
    ]
    for path in paths:
        for _ in range(100):
            response = client.get(path)
            assert response.status_code == 200, (path, response.text[:300])
    for _ in range(100):
        tool = execute_tool("get_forecast_metrics", run_id=latest_run)
        assert tool["meta"]["run_id"] == latest_run
        assert tool["source_type"] == "derived"
    after = _table_snapshot(engine)
    assert after == before


def test_frontend_contract_migrates_fact_status_out_of_global_layout():
    states = (ROOT / "frontend/src/components/common/States.tsx").read_text(encoding="utf-8")
    layout = (ROOT / "frontend/src/layout/BasicLayout.tsx").read_text(encoding="utf-8")
    settings = (ROOT / "frontend/src/pages/settings/SettingsPage.tsx").read_text(encoding="utf-8")
    settings_api = (ROOT / "frontend/src/services/settingsApi.ts").read_text(encoding="utf-8")
    api = (ROOT / "frontend/src/api.ts").read_text(encoding="utf-8")
    assert "SourceContextPanel" in states
    for forbidden_label in ["数据来源", "模拟数据", "真实数据", "测试数据", "Seed 数据"]:
        assert forbidden_label not in states
    for neutral_label in ["业务时间", "更新时间", "批次状态"]:
        assert neutral_label in states
    assert "当前业务信息暂不可用" in states
    assert "当前无可用真实预测" not in states
    assert "FactStatusBar" not in layout
    assert "api.sourceContext()" not in layout
    assert "SourceContextPanel" in settings
    assert "api.sourceContext" in settings_api
    assert "/api/source/context" in api

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from backend.app.api.v1.endpoints.report import _with_report_meta
from backend.app.services.report_generation_service import (
    REPORT_SCHEMA_VERSION,
    ReportGenerationError,
    build_operational_report,
    generate_operational_report,
    render_report_markdown,
)


def _run(run_id: str = "run_phase5_c_unit_00000000000001") -> dict:
    return {
        "run_id": run_id,
        "status": "success",
        "record_count": 24,
        "model_id": "price-model",
        "model_version": "model_20260620_063015",
        "feature_version": "features_140db8af25f9",
        "artifact_id": "artifact_f6689b533cb8fc94e18ac53a",
        "artifact_hash": "a" * 64,
        "schema_hash": "b" * 64,
        "result_hash": "c" * 64,
        "forecast_start_at": datetime(2026, 6, 18, tzinfo=timezone.utc),
        "forecast_end_at": datetime(2026, 6, 18, 23, tzinfo=timezone.utc),
    }


def _rows(run_id: str = "run_phase5_c_unit_00000000000001") -> list[dict]:
    start = datetime(2026, 6, 18, tzinfo=timezone.utc)
    return [
        {
            "run_id": run_id,
            "datetime": start + timedelta(hours=index),
            "predicted_price": -5.0 if index == 2 else 30.0 + index * 2,
            "spike_risk_prob": 0.8 if index in {17, 18} else 0.1,
        }
        for index in range(24)
    ]


def _meta(*, stale: bool = True) -> dict:
    return {
        "source_type": "real",
        "domain": "electricity_day_ahead_price",
        "is_stale": stale,
        "stale_reason": "forecast_window_expired" if stale else None,
    }


def test_report_contract_is_traceable_and_stale_safe() -> None:
    report = build_operational_report(
        _run(),
        _rows(),
        _meta(stale=True),
        report_id="p5c_daily_run_phase5_c_unit_00000000000001",
        report_type="daily",
        region="模型覆盖市场",
        generated_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
    )

    assert report["report_schema_version"] == REPORT_SCHEMA_VERSION
    assert report["source"]["run_id"] == _run()["run_id"]
    assert report["source"]["model_version"] == "model_20260620_063015"
    assert report["source"]["feature_version"] == "features_140db8af25f9"
    assert report["source"]["is_stale"] is True
    assert report["executive_summary"]["record_count"] == 24
    assert report["executive_summary"]["current_use_allowed"] is False
    assert report["executive_summary"]["negative_price_hour_count"] == 1
    assert report["executive_summary"]["spike_risk_hour_count"] == 2
    assert len(report["report_hash"]) == 64
    actions = " ".join(item["action"] for item in report["decision_support"])
    assert "刷新预测" in actions
    assert "不得自动下单" in actions
    markdown = render_report_markdown(report)
    assert report["source"]["run_id"] in markdown
    assert report["report_hash"] in markdown


def test_report_api_meta_preserves_lineage_and_stale_state() -> None:
    payload = _with_report_meta(
        {
            "report_id": "p5c_report",
            "run_id": "run_phase5_c",
            "available": True,
            "generated_at": "2026-07-18T13:15:55Z",
            "metadata": {
                "model_version": "model-v1",
                "feature_version": "features-v1",
                "schema_hash": "schema-v1",
                "result_hash": "result-v1",
                "is_stale": True,
                "stale_reason": "forecast_window_expired",
            },
        }
    )
    assert payload["run_id"] == "run_phase5_c"
    assert payload["model_version"] == "model-v1"
    assert payload["feature_version"] == "features-v1"
    assert payload["is_stale"] is True
    assert payload["stale_reason"] == "forecast_window_expired"
    assert payload["meta"]["evidence"][1]["result_hash"] == "result-v1"


@pytest.mark.parametrize(
    ("run_patch", "rows", "message"),
    [
        ({"status": "failed"}, _rows(), "success"),
        ({"record_count": 23}, _rows()[:23], "24"),
        ({"result_hash": ""}, _rows(), "result_hash"),
    ],
)
def test_report_contract_fails_closed(run_patch: dict, rows: list[dict], message: str) -> None:
    run = _run()
    run.update(run_patch)
    with pytest.raises(ReportGenerationError, match=message):
        build_operational_report(
            run,
            rows,
            _meta(),
            report_id="p5c_daily_failure",
            report_type="daily",
            region="模型覆盖市场",
        )


@pytest.fixture(scope="module")
def postgres_engine():
    url = os.getenv("PHASE5_C_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("PHASE5_C_TEST_DATABASE_URL is not configured")
    engine = create_engine(url, future=True)
    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    compatible_revisions = {
        "0014_t003_run_transaction",
        "0015_phase5d_strategy",
        "0016_strategy_runtime",
        "0017_day6_operational",
    }
    if revision not in compatible_revisions:
        engine.dispose()
        pytest.skip("PHASE5-C integration database is not at a compatible revision")
    yield engine
    engine.dispose()


def _insert_fixture(engine, run_id: str) -> None:
    start = datetime(2026, 7, 20, tzinfo=timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO forecast_runs (
                    run_id, status, domain, target_name, model_id, model_version,
                    artifact_id, artifact_hash, feature_version, schema_hash,
                    input_hash, result_hash, source_type, record_count, row_count,
                    forecast_start_at, forecast_end_at, input_start_at, input_end_at,
                    created_at, started_at, finished_at, environment_hash
                ) VALUES (
                    :run_id, 'success', 'price', 'da_price', 'phase5-c-test-model', 'phase5-c-test-version',
                    'phase5-c-test-artifact', :artifact_hash, 'phase5-c-test-features', :schema_hash,
                    :input_hash, :result_hash, 'real', 24, 24,
                    :start_at, :end_at, :start_at, :end_at,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :environment_hash
                ) ON CONFLICT (run_id) DO NOTHING
                """
            ),
            {
                "run_id": run_id,
                "artifact_hash": "a" * 64,
                "schema_hash": "b" * 64,
                "input_hash": "c" * 64,
                "result_hash": "d" * 64,
                "environment_hash": "e" * 64,
                "start_at": start,
                "end_at": start + timedelta(hours=23),
            },
        )
        for index in range(24):
            conn.execute(
                text(
                    """
                    INSERT INTO forecast_results (
                        run_id, forecast_time, predicted_price, model_version,
                        feature_version, generated_at, spike_risk_prob, source_type, source_row
                    ) VALUES (
                        :run_id, :forecast_time, :predicted_price, 'phase5-c-test-version',
                        'phase5-c-test-features', CURRENT_TIMESTAMP, :risk, 'real', :source_row
                    ) ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "run_id": run_id,
                    "forecast_time": start + timedelta(hours=index),
                    "predicted_price": 25.0 + index,
                    "risk": 0.7 if index == 18 else 0.1,
                    "source_row": index,
                },
            )


def test_postgres_generation_is_idempotent(postgres_engine, tmp_path: Path) -> None:
    run_id = "run_phase5_c_integration_" + uuid.uuid4().hex[:12]
    _insert_fixture(postgres_engine, run_id)
    first = generate_operational_report(
        postgres_engine,
        run_id=run_id,
        report_type="operation_decision",
        output_root=tmp_path,
    )
    second = generate_operational_report(
        postgres_engine,
        run_id=run_id,
        report_type="operation_decision",
        output_root=tmp_path,
    )

    assert first["available"] is True
    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert second["report_id"] == first["report_id"]
    assert Path(first["report_path"]).exists()
    assert Path(first["json_path"]).exists()
    with postgres_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM report_runs WHERE report_id=:report_id"), {"report_id": first["report_id"]}).scalar_one()
    assert count == 1


def test_failure_injection_has_no_half_product(postgres_engine, tmp_path: Path) -> None:
    run_id = "run_phase5_c_failure_" + uuid.uuid4().hex[:12]
    _insert_fixture(postgres_engine, run_id)
    with pytest.raises(ReportGenerationError, match="INJECTED_BEFORE_PERSIST"):
        generate_operational_report(
            postgres_engine,
            run_id=run_id,
            report_type="weekly",
            output_root=tmp_path,
            failure_inject="before_persist",
        )
    report_id = "p5c_weekly_" + run_id
    with postgres_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM report_runs WHERE report_id=:report_id"), {"report_id": report_id}).scalar_one()
    assert count == 0
    assert not list(tmp_path.iterdir())

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from backend.app.services.forecast_transaction_service import (
    ForecastRunRequest,
    ForecastTransactionError,
    ForecastTransactionService,
    PredictionBatch,
    RUN_TRANSITIONS,
    generate_run_id,
)
from model_ops.result_hash import RESULT_VALUE_COLUMNS


DATABASE_URL = os.environ.get("T003_DATABASE_URL", "")
REAL_BATCH_PATH = os.environ.get("T003_REAL_BATCH_PATH", "")
REAL_VALUES_PATH = os.environ.get("T003_REAL_VALUES_PATH", "")
REAL_TIMESTAMPS_PATH = os.environ.get("T003_REAL_TIMESTAMPS_PATH", "")


pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not REAL_BATCH_PATH or not REAL_VALUES_PATH or not REAL_TIMESTAMPS_PATH,
    reason="T003 isolated PostgreSQL and real inference batch are required",
)


@pytest.fixture(scope="module")
def engine():
    value = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
    yield value
    value.dispose()


@pytest.fixture(scope="module")
def batch() -> PredictionBatch:
    import json

    raw = pd.read_csv(REAL_BATCH_PATH, encoding="utf-8-sig")
    timestamps = pd.DatetimeIndex(
        pd.to_datetime(
            json.loads(Path(REAL_TIMESTAMPS_PATH).read_text(encoding="utf-8")),
            utc=True,
        )
    ).tz_convert("America/New_York")
    matrix = np.load(REAL_VALUES_PATH, allow_pickle=False)
    values = pd.DataFrame(matrix, columns=list(RESULT_VALUE_COLUMNS))
    assert raw.shape[0] == matrix.shape[0] == 24
    return PredictionBatch(timestamps, values)


@pytest.fixture(scope="module")
def run_request(batch: PredictionBatch) -> ForecastRunRequest:
    return ForecastRunRequest(
        domain="price",
        target_name="da_price",
        input_start_at=batch.timestamps[0].to_pydatetime(),
        input_end_at=batch.timestamps[-1].to_pydatetime(),
        input_hash=os.environ["T003_INPUT_HASH"],
        environment_hash=os.environ["T003_ENVIRONMENT_HASH"],
        source_type="t003_test_real_inference",
    )


def _counts(engine, run_id: str) -> tuple[str | None, int]:
    with engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM forecast_runs WHERE run_id=:run_id"),
            {"run_id": run_id},
        ).scalar()
        count = conn.execute(
            text("SELECT COUNT(*) FROM forecast_results WHERE run_id=:run_id"),
            {"run_id": run_id},
        ).scalar_one()
    return status, int(count)


def _active(engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT model_id, model_version, artifact_id, artifact_path,
                       artifact_hash, feature_version, schema_hash, source_type
                FROM model_registry
                WHERE domain='price' AND target_name='da_price'
                  AND LOWER(status)='active' AND is_active=1
                """
            )
        ).mappings().one()
    return dict(row)


def test_run_id_is_unique_sortable_and_state_machine_is_closed():
    ids = [generate_run_id() for _ in range(200)]
    assert len(set(ids)) == 200
    assert all(item.startswith("run_") and len(item) == 37 for item in ids)
    assert RUN_TRANSITIONS["created"] == {"validating", "failed", "cancelled"}
    assert RUN_TRANSITIONS["validating"] == {"running", "failed", "cancelled"}
    assert RUN_TRANSITIONS["running"] == {"success", "failed", "cancelled"}
    assert not RUN_TRANSITIONS["success"]


def test_normal_run_idempotency_and_same_input_new_run(
    engine,
    batch: PredictionBatch,
    run_request: ForecastRunRequest,
):
    service = ForecastTransactionService(engine)
    states: list[str] = []
    first = service.execute(run_request, lambda _: batch, state_observer=states.append)
    assert states == ["created", "validating", "running", "success"]
    assert first["status"] == "success"
    assert first["record_count"] == 24
    first_id = str(first["run_id"])
    first_hash = str(first["result_hash"])
    assert _counts(engine, first_id) == ("success", 24)

    repeated = service.execute(run_request, lambda _: batch, run_id=first_id)
    assert repeated["idempotent"] is True
    assert repeated["record_count"] == 24
    assert repeated["result_hash"] == first_hash
    assert _counts(engine, first_id) == ("success", 24)

    second = service.execute(run_request, lambda _: batch)
    second_id = str(second["run_id"])
    assert second_id != first_id
    assert second["result_hash"] == first_hash
    assert _counts(engine, first_id) == ("success", 24)
    assert _counts(engine, second_id) == ("success", 24)
    with engine.connect() as conn:
        latest = conn.execute(
            text(
                """
                SELECT run_id FROM forecast_runs
                WHERE status='success' AND record_count=24
                ORDER BY finished_at DESC, run_id DESC LIMIT 1
                """
            )
        ).scalar_one()
    assert latest == second_id


def test_failure_at_row_12_rolls_back_and_preserves_success(
    engine,
    batch: PredictionBatch,
    run_request: ForecastRunRequest,
):
    service = ForecastTransactionService(engine)
    before_success = service.execute(run_request, lambda _: batch)
    failed_id = generate_run_id()

    def fail_at_12(stage, index, _conn):
        if stage == "before_insert" and index == 12:
            raise ForecastTransactionError("INJECTED_ROW_12_FAILURE", "injected")

    with pytest.raises(ForecastTransactionError, match="injected"):
        service.execute(run_request, lambda _: batch, run_id=failed_id, fault_injector=fail_at_12)
    assert _counts(engine, failed_id) == ("failed", 0)
    assert _counts(engine, str(before_success["run_id"])) == ("success", 24)


@pytest.mark.parametrize(
    ("code", "predictor"),
    [
        ("ARTIFACT_HASH_MISMATCH", lambda _model, batch: (_ for _ in ()).throw(ForecastTransactionError("ARTIFACT_HASH_MISMATCH", "x"))),
        ("FEATURE_VERSION_MISMATCH", lambda _model, batch: (_ for _ in ()).throw(ForecastTransactionError("FEATURE_VERSION_MISMATCH", "x"))),
        ("SCHEMA_HASH_MISMATCH", lambda _model, batch: (_ for _ in ()).throw(ForecastTransactionError("SCHEMA_HASH_MISMATCH", "x"))),
        ("MISSING_FEATURE", lambda _model, batch: (_ for _ in ()).throw(ForecastTransactionError("MISSING_FEATURE", "x"))),
        ("EXTRA_FEATURE", lambda _model, batch: (_ for _ in ()).throw(ForecastTransactionError("EXTRA_FEATURE", "x"))),
        ("TIMEZONE_MISMATCH", lambda _model, batch: (_ for _ in ()).throw(ForecastTransactionError("TIMEZONE_MISMATCH", "x"))),
        ("MODEL_LOAD_FAILED", lambda _model, batch: (_ for _ in ()).throw(ForecastTransactionError("MODEL_LOAD_FAILED", "x"))),
        ("RESULT_COUNT_INVALID", lambda _model, batch: PredictionBatch(batch.timestamps[:23], batch.values.iloc[:23].copy())),
        (
            "RESULT_NONFINITE",
            lambda _model, batch: PredictionBatch(
                batch.timestamps,
                batch.values.assign(predicted_price=lambda frame: frame["predicted_price"].mask(frame.index == 0, np.nan)),
            ),
        ),
        (
            "RESULT_NONFINITE",
            lambda _model, batch: PredictionBatch(
                batch.timestamps,
                batch.values.assign(predicted_price=lambda frame: frame["predicted_price"].mask(frame.index == 0, np.inf)),
            ),
        ),
    ],
)
def test_model_and_contract_failures_leave_only_failed_run(
    engine,
    batch: PredictionBatch,
    run_request: ForecastRunRequest,
    code: str,
    predictor,
):
    run_id = generate_run_id()
    service = ForecastTransactionService(engine)
    with pytest.raises(ForecastTransactionError) as error:
        service.execute(run_request, lambda model: predictor(model, batch), run_id=run_id)
    assert error.value.code == code
    assert _counts(engine, run_id) == ("failed", 0)


def test_active_model_missing_and_conflict_are_fail_closed(
    engine,
    batch: PredictionBatch,
    run_request: ForecastRunRequest,
):
    active = _active(engine)
    for expected, resolver in (
        ("ACTIVE_MODEL_MISSING", lambda *_: []),
        ("ACTIVE_MODEL_CONFLICT", lambda *_: [active, dict(active)]),
    ):
        run_id = generate_run_id()
        service = ForecastTransactionService(engine, model_resolver=resolver)
        with pytest.raises(ForecastTransactionError) as error:
            service.execute(run_request, lambda _: batch, run_id=run_id)
        assert error.value.code == expected
        assert _counts(engine, run_id) == ("failed", 0)


def test_unique_conflict_and_success_update_failure_are_atomic(
    engine,
    batch: PredictionBatch,
    run_request: ForecastRunRequest,
):
    service = ForecastTransactionService(engine)

    def duplicate_first(stage, index, conn):
        if stage == "before_insert" and index == 2:
            conn.execute(
                text(
                    """
                    INSERT INTO forecast_results (
                        run_id, forecast_time, forecast_datetime, predicted_price,
                        model_version, feature_version, generated_at, source_row
                    )
                    SELECT run_id, forecast_time, forecast_datetime, predicted_price,
                           model_version, feature_version, generated_at, 99
                    FROM forecast_results WHERE run_id=:run_id AND source_row=1
                    """
                ),
                {"run_id": current_id},
            )

    current_id = generate_run_id()
    with pytest.raises(ForecastTransactionError) as conflict:
        service.execute(run_request, lambda _: batch, run_id=current_id, fault_injector=duplicate_first)
    assert conflict.value.code == "DATABASE_CONSTRAINT_CONFLICT"
    assert _counts(engine, current_id) == ("failed", 0)

    update_id = generate_run_id()

    def fail_success(stage, _index, _conn):
        if stage == "before_success":
            raise ForecastTransactionError("SUCCESS_STATE_UPDATE_FAILED", "injected")

    with pytest.raises(ForecastTransactionError) as update:
        service.execute(run_request, lambda _: batch, run_id=update_id, fault_injector=fail_success)
    assert update.value.code == "SUCCESS_STATE_UPDATE_FAILED"
    assert _counts(engine, update_id) == ("failed", 0)


def test_current_export_failure_does_not_damage_committed_run(
    engine,
    batch: PredictionBatch,
    run_request: ForecastRunRequest,
):
    service = ForecastTransactionService(engine)

    def broken_export(_run):
        raise OSError("injected export failure")

    result = service.execute(run_request, lambda _: batch, exporter=broken_export)
    assert result["status"] == "success"
    assert result["export_status"] == "failed_after_commit"
    assert _counts(engine, str(result["run_id"])) == ("success", 24)


def test_get_queries_100_times_have_no_side_effects(
    engine,
):
    from backend.app.repositories.forecast_repository import (
        get_forecast_run,
        latest_successful_run,
        list_forecast_runs,
        load_forecast_results,
    )

    latest = latest_successful_run(engine=engine)
    assert latest and latest["run_id"]
    run_id = str(latest["run_id"])
    with engine.connect() as conn:
        before = {
            "runs": conn.execute(text("SELECT COUNT(*) FROM forecast_runs")).scalar_one(),
            "results": conn.execute(text("SELECT COUNT(*) FROM forecast_results")).scalar_one(),
            "hash": conn.execute(
                text("SELECT result_hash FROM forecast_runs WHERE run_id=:run_id"),
                {"run_id": run_id},
            ).scalar_one(),
        }
    for _ in range(100):
        assert latest_successful_run(engine=engine)["run_id"] == run_id
        assert get_forecast_run(run_id, engine=engine)["run_id"] == run_id
        assert len(load_forecast_results(run_id, engine=engine)) == 24
        assert list_forecast_runs(limit=20, engine=engine)
    with engine.connect() as conn:
        after = {
            "runs": conn.execute(text("SELECT COUNT(*) FROM forecast_runs")).scalar_one(),
            "results": conn.execute(text("SELECT COUNT(*) FROM forecast_results")).scalar_one(),
            "hash": conn.execute(
                text("SELECT result_hash FROM forecast_runs WHERE run_id=:run_id"),
                {"run_id": run_id},
            ).scalar_one(),
        }
    assert after == before


def test_forecast_api_contract_uses_postgresql_success_runs(engine):
    from fastapi.testclient import TestClient

    from backend.app.core.config import reset_settings_cache
    from backend.app.db.session import reset_db_cache
    from backend.app.main import app

    reset_settings_cache()
    reset_db_cache()
    client = TestClient(app)
    latest_response = client.get("/api/forecast/runs/latest-success")
    assert latest_response.status_code == 200
    latest = latest_response.json()
    assert latest["available"] is True
    run_id = latest["run"]["run_id"]
    assert latest["run"]["status"] == "success"
    assert latest["run"]["record_count"] == 24

    detail = client.get(f"/api/forecast/runs/{run_id}")
    results = client.get(f"/api/forecast/runs/{run_id}/results")
    history = client.get("/api/forecast/runs?limit=20")
    compatibility = client.get(f"/api/forecast/{run_id}")
    assert detail.status_code == results.status_code == history.status_code == compatibility.status_code == 200
    assert detail.json()["run"]["run_id"] == run_id
    assert results.json()["record_count"] == 24
    assert len(results.json()["records"]) == 24
    assert history.json()["items"]
    assert compatibility.json()["run_id"] == run_id
    assert compatibility.json()["source"] == "postgresql.forecast_runs"

    with engine.connect() as conn:
        failed = conn.execute(
            text(
                """
                SELECT run_id, error_message FROM forecast_runs
                WHERE status='failed' ORDER BY finished_at DESC NULLS LAST, created_at DESC LIMIT 1
                """
            )
        ).mappings().first()
    assert failed
    failed_detail = client.get(f"/api/forecast/runs/{failed['run_id']}")
    assert failed_detail.status_code == 200
    payload = failed_detail.json()["run"]
    assert payload["status"] == "failed"
    assert payload["error_message"] == "预测事务失败，未提交任何预测结果。"
    assert "postgresql://" not in payload["error_message"]
    assert "E:\\" not in payload["error_message"]


def test_legacy_delete_reload_and_synthetic_fallback_are_blocked(engine):
    from backend.app.services.core_data_sync import sync_forecast_facts
    from backend.app.services.task_business_handlers import _write_backend_forecast

    with engine.connect() as conn:
        before = (
            conn.execute(text("SELECT COUNT(*) FROM forecast_runs")).scalar_one(),
            conn.execute(text("SELECT COUNT(*) FROM forecast_results")).scalar_one(),
        )
    result = sync_forecast_facts(engine=engine)
    assert result["blocked"] is True
    assert result["forecast_runs_written"] == 0
    assert result["forecast_results_written"] == 0
    with pytest.raises(RuntimeError, match="合成预测回退已禁用"):
        _write_backend_forecast({}, None)
    with engine.connect() as conn:
        after = (
            conn.execute(text("SELECT COUNT(*) FROM forecast_runs")).scalar_one(),
            conn.execute(text("SELECT COUNT(*) FROM forecast_results")).scalar_one(),
        )
    assert after == before
    sources = (
        Path("backend/app/services/core_data_sync.py").read_text(encoding="utf-8")
        + Path("backend/app/services/task_business_handlers.py").read_text(encoding="utf-8")
    ).lower()
    assert "delete from forecast_results" not in sources
    assert "delete from forecast_runs" not in sources

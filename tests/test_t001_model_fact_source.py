from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError

from backend.app.main import app
from backend.app.repositories import model_repository
from backend.app.services.core_data_sync import sync_model_facts
from backend.app.services.model_fact_service import ModelFactError, ModelFactService
from model_ops import active_model_loader


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "migrations" / "versions" / "0013_t001_model_fact_source.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("t001_migration", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_legacy_schema(engine: sa.Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE model_registry (
                    model_version VARCHAR(64) PRIMARY KEY,
                    model_role VARCHAR(32) NOT NULL,
                    train_start_date DATE,
                    train_end_date DATE,
                    feature_version VARCHAR(64),
                    artifact_path VARCHAR(500) NOT NULL,
                    test_mae NUMERIC(12,6),
                    test_rmse NUMERIC(12,6),
                    peak_rmse NUMERIC(12,6),
                    spike_rmse NUMERIC(12,6),
                    rolling_rmse NUMERIC(12,6),
                    is_active SMALLINT NOT NULL DEFAULT 0,
                    status VARCHAR(32) NOT NULL DEFAULT 'candidate',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    activated_at TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE model_versions (
                    id INTEGER PRIMARY KEY,
                    model_version VARCHAR(128) NOT NULL UNIQUE,
                    status VARCHAR(32),
                    is_active BOOLEAN,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO model_versions (id, model_version, status, is_active) "
                "VALUES (1, 'legacy-seed-active', 'Active', 1)"
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE prediction_tracking (
                    id INTEGER PRIMARY KEY, model_version VARCHAR(64), actual_price REAL,
                    abs_error REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE model_metrics (
                    id INTEGER PRIMARY KEY, model_version VARCHAR(128), metric_date DATE,
                    mae REAL, rmse REAL, r2 REAL, mape REAL, peak_error REAL,
                    sample_count INTEGER, metrics_json TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE task_runs (
                    task_id VARCHAR(64) PRIMARY KEY, task_name VARCHAR(128), task_kind VARCHAR(64),
                    status VARCHAR(32), payload_json TEXT, started_at TIMESTAMP, ended_at TIMESTAMP,
                    duration_seconds REAL, created_at TIMESTAMP, updated_at TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE model_governance_events (
                    id INTEGER PRIMARY KEY, event_id VARCHAR(64), action VARCHAR(64),
                    target_version VARCHAR(128), source_version VARCHAR(128), operator VARCHAR(128),
                    reason TEXT, status VARCHAR(32), metadata_json TEXT, created_at TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE model_prediction_comparison_points (
                    id INTEGER PRIMARY KEY, model_type VARCHAR(64), region VARCHAR(64),
                    forecast_time TIMESTAMP, active_version VARCHAR(128), candidate_version VARCHAR(128),
                    actual_value REAL, active_prediction REAL, candidate_prediction REAL,
                    diff_value REAL, data_origin VARCHAR(32)
                )
                """
            )
        )


def _apply_migration(engine: sa.Engine, monkeypatch: pytest.MonkeyPatch):
    module = _migration_module()
    with engine.begin() as conn:
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(conn)))
        module.upgrade()
    return module


@pytest.fixture
def isolated_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> sa.Engine:
    engine = sa.create_engine(f"sqlite+pysqlite:///{tmp_path / 't001.sqlite'}", future=True)
    _create_legacy_schema(engine)
    _apply_migration(engine, monkeypatch)
    yield engine
    engine.dispose()


def _candidate(version: str, *, domain: str = "price", target_name: str = "da_price") -> dict:
    return {
        "model_id": f"id-{version}",
        "model_version": version,
        "domain": domain,
        "target_name": target_name,
        "model_role": domain,
        "artifact_id": f"artifact-{version}",
        "artifact_path": f"model_artifacts/{version}",
        "feature_version": "features-test",
        "schema_hash": hashlib.sha256(f"schema:{version}".encode()).hexdigest(),
        "source_type": "test",
    }


def _snapshot(engine: sa.Engine) -> str:
    with engine.connect() as conn:
        registry = conn.execute(
            text(
                """
                SELECT model_id, model_version, domain, target_name, status, is_active,
                       created_at, validated_at, activated_at, deactivated_at, source_type
                FROM model_registry ORDER BY model_version
                """
            )
        ).all()
        legacy = conn.execute(
            text("SELECT id, model_version, status, is_active, updated_at FROM model_versions ORDER BY id")
        ).all()
    payload = {"registry": [tuple(row) for row in registry], "legacy": [tuple(row) for row in legacy]}
    return hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest()


def test_migration_upgrade_downgrade_is_non_destructive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = sa.create_engine(f"sqlite+pysqlite:///{tmp_path / 'migration.sqlite'}", future=True)
    _create_legacy_schema(engine)
    with engine.connect() as conn:
        before = {
            "registry": conn.execute(text("SELECT COUNT(*) FROM model_registry")).scalar_one(),
            "versions": conn.execute(text("SELECT COUNT(*) FROM model_versions")).scalar_one(),
        }
    module = _apply_migration(engine, monkeypatch)
    inspector = sa.inspect(engine)
    columns = {item["name"] for item in inspector.get_columns("model_registry")}
    indexes = {item["name"] for item in inspector.get_indexes("model_registry")}
    assert {"model_id", "domain", "target_name", "artifact_id", "schema_hash", "validated_at", "deactivated_at", "source_type"} <= columns
    assert "uq_model_registry_active_domain_target" in indexes
    assert "uq_model_registry_model_id" in indexes
    with engine.begin() as conn:
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(conn)))
        module.downgrade()
    indexes_after = {item["name"] for item in sa.inspect(engine).get_indexes("model_registry")}
    assert "uq_model_registry_active_domain_target" not in indexes_after
    assert "model_id" in {item["name"] for item in sa.inspect(engine).get_columns("model_registry")}
    with engine.connect() as conn:
        after = {
            "registry": conn.execute(text("SELECT COUNT(*) FROM model_registry")).scalar_one(),
            "versions": conn.execute(text("SELECT COUNT(*) FROM model_versions")).scalar_one(),
        }
    assert after == before == {"registry": 0, "versions": 1}
    engine.dispose()


def test_lifecycle_unique_active_rollback_and_domain_isolation(isolated_engine: sa.Engine):
    service = ModelFactService(isolated_engine)
    first = service.register_candidate(_candidate("model_20260620_063015"))
    assert first["status"] == "candidate" and first["is_active"] is False
    with pytest.raises(ModelFactError, match="validated"):
        service.activate_model(first["model_version"], "price", "da_price")

    service.validate_candidate(first["model_version"], "price", "da_price")
    assert service.activate_model(first["model_version"], "price", "da_price")["status"] == "active"

    second = service.register_candidate(_candidate("price-v2"))
    service.mark_validating(second["model_version"], "price", "da_price")
    service.validate_candidate(second["model_version"], "price", "da_price")
    service.activate_model(second["model_version"], "price", "da_price")
    assert service.get_model(first["model_version"], "price", "da_price")["status"] == "archived"
    assert service.get_active_model("price", "da_price")["model_version"] == "price-v2"

    service.rollback_active_model(first["model_version"], "price", "da_price")
    assert service.get_active_model("price", "da_price")["model_version"] == first["model_version"]

    load = service.register_candidate(_candidate("load-v1", domain="load", target_name="actual_load"))
    service.validate_candidate(load["model_version"], "load", "actual_load")
    service.activate_model(load["model_version"], "load", "actual_load")
    assert service.get_active_model("load", "actual_load")["model_version"] == "load-v1"
    assert all(item["domain"] == "price" for item in service.list_models("price", "da_price"))
    assert all(item["domain"] == "load" for item in service.list_models("load", "actual_load"))
    with pytest.raises(ModelFactError):
        service.list_models("", "da_price")

    with pytest.raises(IntegrityError):
        with isolated_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO model_registry (
                        model_id, model_version, domain, target_name, model_role,
                        artifact_path, status, is_active, source_type
                    ) VALUES ('duplicate-id', 'duplicate-active', 'price', 'da_price', 'price',
                              'model_artifacts/duplicate', 'active', 1, 'test')
                    """
                )
            )


def test_activation_failure_rolls_back_entire_transaction(isolated_engine: sa.Engine):
    service = ModelFactService(isolated_engine)
    for version in ("stable-v1", "candidate-v2"):
        service.register_candidate(_candidate(version))
        service.validate_candidate(version, "price", "da_price")
    service.activate_model("stable-v1", "price", "da_price")

    def fail_target_activation(_conn, _cursor, statement, _params, _context, _many):
        normalized = " ".join(statement.lower().split())
        if normalized.startswith("update model_registry set status = 'active'"):
            raise RuntimeError("injected activation failure")

    event.listen(isolated_engine, "before_cursor_execute", fail_target_activation)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            service.activate_model("candidate-v2", "price", "da_price")
    finally:
        event.remove(isolated_engine, "before_cursor_execute", fail_target_activation)

    assert service.get_active_model("price", "da_price")["model_version"] == "stable-v1"
    assert service.get_model("candidate-v2", "price", "da_price")["status"] == "validated"


def test_empty_registry_never_falls_back_to_legacy_model_versions(isolated_engine: sa.Engine):
    service = ModelFactService(isolated_engine)
    assert service.list_models("price", "da_price") == []
    assert service.get_active_model("price", "da_price") == {}
    with isolated_engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM model_versions")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM model_registry")).scalar_one() == 0


def test_prediction_active_lookup_uses_registry_without_local_fallback(
    isolated_engine: sa.Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    service = ModelFactService(isolated_engine)
    service.register_candidate(_candidate("prediction-active"))
    service.validate_candidate("prediction-active", "price", "da_price")
    service.activate_model("prediction-active", "price", "da_price")
    monkeypatch.setattr(active_model_loader, "get_database_config", lambda _config: SimpleNamespace(enabled=True))
    monkeypatch.setattr(active_model_loader, "create_database_engine", lambda _config: isolated_engine)
    config = {"model_learning": {"domain": "price", "target_name": "da_price", "active_artifact_path": "must-not-fallback"}}
    assert active_model_loader.get_active_model_record(config)["model_version"] == "prediction-active"
    service.deactivate_model("prediction-active", "price", "da_price")
    with pytest.raises(active_model_loader.ActiveModelUnavailable, match="不会回退"):
        active_model_loader.get_active_model_record(config)


def test_legacy_model_sync_is_fail_closed_and_does_not_write(isolated_engine: sa.Engine):
    before = _snapshot(isolated_engine)
    writes: list[str] = []

    def record_sql(_conn, _cursor, statement, _params, _context, _many):
        verb = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        if verb in {"INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "TRUNCATE"}:
            writes.append(verb)

    event.listen(isolated_engine, "before_cursor_execute", record_sql)
    try:
        result = sync_model_facts(engine=isolated_engine)
    finally:
        event.remove(isolated_engine, "before_cursor_execute", record_sql)
    assert result["blocked"] is True
    assert result["model_versions_written"] == 0
    assert writes == []
    assert _snapshot(isolated_engine) == before


def test_get_list_detail_and_active_100_times_have_no_write_side_effects(
    isolated_engine: sa.Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    service = ModelFactService(isolated_engine)
    service.register_candidate(_candidate("read-stable"))
    service.validate_candidate("read-stable", "price", "da_price")
    service.activate_model("read-stable", "price", "da_price")
    service.register_candidate(_candidate("read-candidate"))
    before = _snapshot(isolated_engine)
    writes: list[str] = []

    def record_sql(_conn, _cursor, statement, _params, _context, _many):
        verb = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        if verb in {"INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "TRUNCATE"}:
            writes.append(verb)

    event.listen(isolated_engine, "before_cursor_execute", record_sql)
    monkeypatch.setattr(model_repository, "postgres_engine", lambda: isolated_engine)
    client = TestClient(app)
    try:
        for _ in range(100):
            response = client.get("/api/models/center/overview?domain=price&target_name=da_price")
            assert response.status_code == 200
            assert response.json()["data_lineage"]["versions"] == "postgresql.model_registry"
        for _ in range(100):
            response = client.get("/api/models/center/versions/read-stable?domain=price&target_name=da_price")
            assert response.status_code == 200 and response.json()["version"]["status"] == "active"
        for _ in range(100):
            response = client.get("/api/models/active?domain=price&target_name=da_price")
            assert response.status_code == 200 and response.json()["active"]["model_version"] == "read-stable"
    finally:
        event.remove(isolated_engine, "before_cursor_execute", record_sql)

    assert writes == []
    assert _snapshot(isolated_engine) == before
    with isolated_engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM model_versions")).scalar_one() == 1

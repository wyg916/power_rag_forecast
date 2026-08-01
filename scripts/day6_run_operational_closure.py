from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.security import CurrentUser
from backend.app.repositories.strategy_repository import transition_strategy
from backend.app.services.forecast_transaction_service import (
    ForecastRunRequest,
    ForecastTransactionService,
    PredictionBatch,
)
from backend.app.services.report_generation_service import generate_operational_report
from backend.app.services.strategy_governance_service import generate_strategy_draft
from prediction_engine.day6_operational import (
    BUSINESS_TIMEZONE,
    PROVIDER_CONTRACT_VERSION,
    TARGET_FIELD,
    TIME_FIELD,
    build_feature_frame,
    canonical_sha256,
    feature_contract,
    feature_names,
    feature_specs,
    fetch_live_load_forecast,
    fetch_live_price_history,
    fetch_live_weather,
    forecast_window,
    verify_24h_continuity,
)


LOGIN_ROLE = "beta10d_forecast_login"
ENVIRONMENT = "development_demo"


def read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def validate_runtime(url: str) -> None:
    parsed = urlsplit(url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.hostname not in {"localhost", "127.0.0.1"} or (parsed.port or 5432) != 5432:
        raise RuntimeError("database_target_not_allowed")
    if parsed.path.lstrip("/") != "postgres" or parsed.username != LOGIN_ROLE:
        raise RuntimeError("restricted_runtime_identity_required")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def candidate_model(conn, model_version: str) -> dict[str, object]:
    row = conn.execute(
        text(
            """
            SELECT model_id,model_version,artifact_id,artifact_path,artifact_hash,
                   feature_version,schema_hash,source_type,status,is_active
            FROM model_registry
            WHERE model_version=:model_version AND status='validated' AND is_active=0
            """
        ),
        {"model_version": model_version},
    ).mappings().first()
    if not row:
        raise RuntimeError("validated_non_active_candidate_missing")
    return dict(row)


def users() -> tuple[CurrentUser, CurrentUser]:
    creator = CurrentUser(
        user_id="day6_demo_operator",
        username="day6_demo_operator",
        role="analyst",
        permissions=["strategy:generate", "strategy:submit"],
        auth_mode="day6_development_demo",
    )
    reviewer = CurrentUser(
        user_id="day6_demo_reviewer",
        username="day6_demo_reviewer",
        role="reviewer",
        permissions=["strategy:review", "report:review"],
        auth_mode="day6_development_demo",
    )
    return creator, reviewer


def deterministic_ids(anchor: datetime, model_version: str, feature_version: str) -> tuple[str, str, str]:
    id_anchor = anchor.replace(minute=0, second=0, microsecond=0)
    basis = {
        "anchor_hour": id_anchor.astimezone(timezone.utc).isoformat(),
        "model_version": model_version,
        "feature_version": feature_version,
        "environment": ENVIRONMENT,
    }
    idempotency_key = canonical_sha256(basis)
    run_id = f"run_{id_anchor.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_{idempotency_key[:10]}"
    batch_id = f"batch_day6_{idempotency_key[:32]}"
    return run_id, batch_id, idempotency_key


def model_resolver(model_version: str):
    def resolve(conn, domain: str, target_name: str) -> list[dict[str, object]]:
        if domain != "price" or target_name != "da_price":
            return []
        return [candidate_model(conn, model_version)]

    return resolve


def snapshot_values(features: pd.DataFrame) -> list[list[dict[str, object]]]:
    specs = feature_specs()
    snapshots: list[list[dict[str, object]]] = []
    for _, row in features.iterrows():
        snapshots.append(
            [
                {
                    "position": position,
                    "feature_name": spec.name,
                    "dtype": spec.dtype,
                    "value": int(row[spec.name]) if spec.dtype == "int64" else float(row[spec.name]),
                }
                for position, spec in enumerate(specs)
            ]
        )
    return snapshots


def persist_input_batch(
    engine,
    *,
    run_id: str,
    batch_id: str,
    idempotency_key: str,
    anchor: datetime,
    targets: pd.DatetimeIndex,
    features: pd.DataFrame,
    provider_metadata: dict[str, object],
    contract: dict[str, object],
) -> dict[str, object]:
    ordered_snapshots = snapshot_values(features)
    feature_hashes = [canonical_sha256(item) for item in ordered_snapshots]
    input_hash = canonical_sha256(
        {
            "run_id": run_id,
            "timestamps": [item.tz_convert("UTC").isoformat() for item in targets],
            "feature_hashes": feature_hashes,
            "schema_hash": contract["schema_hash"],
        }
    )
    source_versions = {
        name: metadata.get("source_version")
        for name, metadata in provider_metadata.items()
        if isinstance(metadata, dict)
    }
    source_hashes = {
        name: metadata.get("source_hash")
        for name, metadata in provider_metadata.items()
        if isinstance(metadata, dict)
    }
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT * FROM forecast_input_batches WHERE idempotency_key=:key FOR UPDATE"),
            {"key": idempotency_key},
        ).mappings().first()
        if existing:
            if str(existing["run_id"]) != run_id or str(existing["schema_hash"]) != str(contract["schema_hash"]):
                raise RuntimeError("input_batch_idempotency_conflict")
            count = conn.execute(
                text("SELECT COUNT(*) FROM forecast_input_snapshots WHERE batch_id=:batch_id"),
                {"batch_id": batch_id},
            ).scalar_one()
            if int(count) != 24:
                raise RuntimeError("existing_input_snapshot_count_invalid")
            return {"input_hash": input_hash, "created": False, "source_hashes": dict(existing["source_hashes"])}
        conn.execute(
            text(
                """
                INSERT INTO forecast_input_batches (
                    batch_id,idempotency_key,run_id,anchor_time,data_cutoff_time,
                    forecast_start,forecast_end,timezone,source_versions,source_hashes,
                    source_metadata,feature_version,schema_hash,row_count,
                    continuity_status,quality_status,environment
                ) VALUES (
                    :batch_id,:idempotency_key,:run_id,:anchor,:anchor,
                    :forecast_start,:forecast_end,:timezone,CAST(:source_versions AS jsonb),
                    CAST(:source_hashes AS jsonb),CAST(:source_metadata AS jsonb),
                    :feature_version,:schema_hash,24,'complete','ready',:environment
                )
                """
            ),
            {
                "batch_id": batch_id,
                "idempotency_key": idempotency_key,
                "run_id": run_id,
                "anchor": anchor,
                "forecast_start": targets[0].to_pydatetime(),
                "forecast_end": targets[-1].to_pydatetime(),
                "timezone": BUSINESS_TIMEZONE,
                "source_versions": json.dumps(source_versions, ensure_ascii=False, default=str),
                "source_hashes": json.dumps(source_hashes, ensure_ascii=False, default=str),
                "source_metadata": json.dumps(provider_metadata, ensure_ascii=False, default=str),
                "feature_version": contract["feature_version"],
                "schema_hash": contract["schema_hash"],
                "environment": ENVIRONMENT,
            },
        )
        for position, timestamp in enumerate(targets):
            values = ordered_snapshots[position]
            conn.execute(
                text(
                    """
                    INSERT INTO forecast_input_snapshots (
                        snapshot_id,batch_id,run_id,forecast_time,feature_position_count,
                        feature_values,feature_hash,source_status
                    ) VALUES (
                        :snapshot_id,:batch_id,:run_id,:forecast_time,:feature_count,
                        CAST(:feature_values AS jsonb),:feature_hash,CAST(:source_status AS jsonb)
                    )
                    """
                ),
                {
                    "snapshot_id": f"snapshot_{feature_hashes[position][:40]}",
                    "batch_id": batch_id,
                    "run_id": run_id,
                    "forecast_time": timestamp.to_pydatetime(),
                    "feature_count": len(values),
                    "feature_values": json.dumps(values, ensure_ascii=False),
                    "feature_hash": feature_hashes[position],
                    "source_status": json.dumps(
                        {"providers": list(provider_metadata), "status": "available_at_prediction_time"},
                        ensure_ascii=False,
                    ),
                },
            )
    return {"input_hash": input_hash, "created": True, "source_hashes": source_hashes}


def existing_batch(engine, idempotency_key: str) -> dict[str, object] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM forecast_input_batches WHERE idempotency_key=:key"),
            {"key": idempotency_key},
        ).mappings().first()
    return dict(row) if row else None


def ensure_report_review(engine, report_id: str, run_id: str) -> dict[str, object]:
    reviewer = "day6_demo_report_reviewer"
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT * FROM report_reviews
                WHERE report_id=:report_id AND action='approve' AND reviewer=:reviewer
                ORDER BY created_at LIMIT 1
                """
            ),
            {"report_id": report_id, "reviewer": reviewer},
        ).mappings().first()
        if row:
            return {**dict(row), "idempotent": True}
        created = conn.execute(
            text(
                """
                INSERT INTO report_reviews (report_id,action,reviewer,comment,metadata_json)
                VALUES (:report_id,'approve',:reviewer,:comment,CAST(:metadata AS jsonb))
                RETURNING *
                """
            ),
            {
                "report_id": report_id,
                "reviewer": reviewer,
                "comment": "Day 6 开发/演示审核：证据链完整；不代表生产发布或市场执行。",
                "metadata": json.dumps(
                    {
                        "run_id": run_id,
                        "review_type": "development_demo_operator_review",
                        "actual_market_execution": False,
                        "production_approval": False,
                    },
                    ensure_ascii=False,
                ),
            },
        ).mappings().one()
    return {**dict(created), "idempotent": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-config", type=Path, required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    runtime_url = read_env(args.runtime_config).get("DATABASE_URL", "")
    validate_runtime(runtime_url)
    engine = create_engine(runtime_url, pool_pre_ping=True, future=True)
    with engine.connect() as conn:
        identity = dict(
            conn.execute(
                text(
                    "SELECT current_user,session_user,r.rolsuper,r.rolcreatedb,r.rolcreaterole,"
                    "r.rolreplication,r.rolbypassrls FROM pg_roles r WHERE r.rolname=current_user"
                )
            ).mappings().one()
        )
        candidate = candidate_model(conn, args.model_version)
    if identity["current_user"] != LOGIN_ROLE or any(
        identity[name] for name in ("rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication", "rolbypassrls")
    ):
        raise RuntimeError("runtime_identity_gate_failed")
    artifact_dir = (args.artifact_root / args.model_version).resolve()
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    thresholds = json.loads((artifact_dir / "thresholds.json").read_text(encoding="utf-8"))
    model_path = artifact_dir / "model.joblib"
    if file_sha256(model_path) != manifest["artifact_hash"] or manifest["artifact_hash"] != candidate["artifact_hash"]:
        raise RuntimeError("artifact_hash_mismatch")
    contract = feature_contract()
    if manifest["feature_version"] != contract["feature_version"] or manifest["schema_hash"] != contract["schema_hash"]:
        raise RuntimeError("feature_contract_mismatch")
    if json.loads((artifact_dir / "feature_cols.json").read_text(encoding="utf-8")) != feature_names():
        raise RuntimeError("feature_order_mismatch")
    anchor, targets = forecast_window()
    verify_24h_continuity(targets)
    run_id, batch_id, idempotency_key = deterministic_ids(
        anchor, args.model_version, str(contract["feature_version"])
    )
    batch = existing_batch(engine, idempotency_key)
    provider_metadata: dict[str, object] = {}
    features: pd.DataFrame | None = None
    if batch is None:
        weather, weather_meta = fetch_live_weather(targets)
        load, load_meta = fetch_live_load_forecast(anchor, targets)
        prices, price_meta = fetch_live_price_history(anchor)
        provider_metadata = {
            "weather_forecast": weather_meta,
            "load_forecast": load_meta,
            "price_history": price_meta,
            "calendar": {
                "source_name": "deterministic_calendar",
                "source_version": contract["calendar_version"],
                "source_hash": canonical_sha256([item.isoformat() for item in targets]),
                "source_generated_at": anchor.isoformat(),
                "valid_from": targets[0].isoformat(),
                "valid_to": targets[-1].isoformat(),
                "row_count": 24,
            },
        }
        features = build_feature_frame(
            price_history=prices,
            load_forecast=load,
            weather_forecast=weather,
            targets=targets,
        )
        persisted = persist_input_batch(
            engine,
            run_id=run_id,
            batch_id=batch_id,
            idempotency_key=idempotency_key,
            anchor=anchor,
            targets=targets,
            features=features,
            provider_metadata=provider_metadata,
            contract=contract,
        )
        input_hash = str(persisted["input_hash"])
    else:
        if str(batch["run_id"]) != run_id or str(batch["batch_id"]) != batch_id:
            raise RuntimeError("existing_batch_identity_mismatch")
        provider_metadata = dict(batch["source_metadata"])
        with engine.connect() as conn:
            snapshot_hashes = conn.execute(
                text(
                    "SELECT forecast_time,feature_hash FROM forecast_input_snapshots "
                    "WHERE batch_id=:batch_id ORDER BY forecast_time"
                ),
                {"batch_id": batch_id},
            ).all()
        if len(snapshot_hashes) != 24:
            raise RuntimeError("existing_input_snapshot_count_invalid")
        input_hash = canonical_sha256(
            {
                "run_id": run_id,
                "timestamps": [row[0].isoformat() for row in snapshot_hashes],
                "feature_hashes": [row[1] for row in snapshot_hashes],
                "schema_hash": contract["schema_hash"],
            }
        )
    model = joblib.load(model_path)

    def predict(_: dict[str, object]) -> PredictionBatch:
        if features is None:
            raise RuntimeError("prediction_features_unavailable_for_new_run")
        predicted = np.asarray(model.predict(features[feature_names()]), dtype="float64")
        residual_q90 = float(thresholds["residual_abs_q90"])
        lag_delta = np.abs(predicted - features["da_price_lag_24"].to_numpy(dtype="float64"))
        spike = np.clip(lag_delta / max(residual_q90 * 3.0, 1e-9), 0.0, 1.0)
        values = pd.DataFrame(
            {
                "base_prediction": predicted,
                "peak_prediction": predicted,
                "classifier_prediction": predicted,
                "spike_probability": spike,
                "p90_prediction": predicted + residual_q90,
                "blend_weight": np.ones(24, dtype="float64"),
                "predicted_price": predicted,
                "forecast_load": features["forecast_load"].to_numpy(dtype="float64"),
                "risk_level": np.where(spike >= 0.5, "high", np.where(spike >= 0.25, "medium", "low")),
            }
        )
        return PredictionBatch(timestamps=targets, values=values)

    request = ForecastRunRequest(
        domain="price",
        target_name="da_price",
        input_start_at=targets[0].to_pydatetime(),
        input_end_at=targets[-1].to_pydatetime(),
        input_hash=input_hash,
        environment_hash=canonical_sha256(
            {"environment": ENVIRONMENT, "provider_contract": PROVIDER_CONTRACT_VERSION}
        ),
        source_type="real",
        input_batch_id=batch_id,
        source_metadata=provider_metadata,
        freshness_status="current",
        development_mode=True,
    )
    service = ForecastTransactionService(engine, model_resolver=model_resolver(args.model_version))
    try:
        forecast = service.execute(request, predict, run_id=run_id)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE forecast_input_batches SET quality_status='success',updated_at=CURRENT_TIMESTAMP "
                    "WHERE batch_id=:batch_id"
                ),
                {"batch_id": batch_id},
            )
    except Exception:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE forecast_input_batches SET quality_status='failed',updated_at=CURRENT_TIMESTAMP "
                    "WHERE batch_id=:batch_id"
                ),
                {"batch_id": batch_id},
            )
        raise
    report = generate_operational_report(
        engine,
        run_id=run_id,
        report_type="operation_decision",
        region="PJM Dominion / Richmond, VA",
        output_root=args.output_root,
    )
    report_review = ensure_report_review(engine, str(report["report_id"]), run_id)
    creator, reviewer = users()
    draft = generate_strategy_draft(
        run_id,
        str(report["report_id"]),
        created_by=creator.username,
        engine=engine,
        citations=[
            {
                "document_id": "postgresql",
                "chunk_id": f"forecast_runs:{run_id}",
                "quote": f"forecast_runs.run_id={run_id}",
            },
            {
                "document_id": "postgresql",
                "chunk_id": f"report_runs:{report['report_id']}",
                "quote": f"report_runs.report_id={report['report_id']}",
            },
        ],
    )
    strategy_id = str(draft["strategy"]["strategy_id"])
    submit = transition_strategy(
        strategy_id,
        "submit",
        request_id=f"d6submit:{canonical_sha256(strategy_id)[:48]}",
        comment="Day 6 开发/演示策略提交审核；禁止自动交易。",
        user=creator,
        engine=engine,
    )
    approve = transition_strategy(
        strategy_id,
        "approve",
        request_id=f"d6approve:{canonical_sha256(strategy_id)[:47]}",
        comment="Day 6 开发/演示审核通过；不构成生产发布或市场执行授权。",
        user=reviewer,
        engine=engine,
    )
    with engine.connect() as conn:
        counts = {
            "input_batch_rows": int(conn.execute(text("SELECT COUNT(*) FROM forecast_input_batches WHERE batch_id=:id"), {"id": batch_id}).scalar_one()),
            "input_snapshot_rows": int(conn.execute(text("SELECT COUNT(*) FROM forecast_input_snapshots WHERE batch_id=:id"), {"id": batch_id}).scalar_one()),
            "forecast_run_rows": int(conn.execute(text("SELECT COUNT(*) FROM forecast_runs WHERE run_id=:id"), {"id": run_id}).scalar_one()),
            "forecast_result_rows": int(conn.execute(text("SELECT COUNT(*) FROM forecast_results WHERE run_id=:id"), {"id": run_id}).scalar_one()),
            "report_rows": int(conn.execute(text("SELECT COUNT(*) FROM report_runs WHERE report_id=:id"), {"id": report["report_id"]}).scalar_one()),
            "report_review_rows": int(conn.execute(text("SELECT COUNT(*) FROM report_reviews WHERE report_id=:id"), {"id": report["report_id"]}).scalar_one()),
            "strategy_rows": int(conn.execute(text("SELECT COUNT(*) FROM strategy_advice WHERE strategy_id=:id"), {"id": strategy_id}).scalar_one()),
            "strategy_review_rows": int(conn.execute(text("SELECT COUNT(*) FROM strategy_reviews WHERE strategy_id=:id"), {"id": strategy_id}).scalar_one()),
        }
        active = conn.execute(
            text(
                "SELECT model_version,feature_version,status,is_active FROM model_registry "
                "WHERE status='active' OR is_active=1 ORDER BY created_at"
            )
        ).mappings().all()
    result = {
        "environment": ENVIRONMENT,
        "production_switched": False,
        "runtime_identity": identity,
        "model_version": args.model_version,
        "feature_version": contract["feature_version"],
        "artifact_hash": manifest["artifact_hash"],
        "input_batch_id": batch_id,
        "input_hash": input_hash,
        "run_id": run_id,
        "forecast_status": forecast.get("status"),
        "forecast_idempotent": forecast.get("idempotent"),
        "result_hash": forecast.get("result_hash"),
        "report_id": report["report_id"],
        "report_hash": report["report_hash"],
        "report_review_id": report_review.get("id"),
        "strategy_id": strategy_id,
        "strategy_status": approve["strategy"]["status"],
        "strategy_published": approve["strategy"]["status"] == "published",
        "submit_review_id": submit["review"]["review_id"],
        "approve_review_id": approve["review"]["review_id"],
        "counts": counts,
        "active_models_after": [dict(row) for row in active],
        "providers": {
            name: {
                "source_name": metadata.get("source_name"),
                "source_version": metadata.get("source_version"),
                "source_generated_at": metadata.get("source_generated_at"),
                "fetched_at": metadata.get("fetched_at"),
                "valid_from": metadata.get("valid_from"),
                "valid_to": metadata.get("valid_to"),
                "row_count": metadata.get("row_count"),
                "source_hash": metadata.get("source_hash"),
            }
            for name, metadata in provider_metadata.items()
            if isinstance(metadata, dict)
        },
        "pass": counts == {
            "input_batch_rows": 1,
            "input_snapshot_rows": 24,
            "forecast_run_rows": 1,
            "forecast_result_rows": 24,
            "report_rows": 1,
            "report_review_rows": 1,
            "strategy_rows": 1,
            "strategy_review_rows": 2,
        }
        and forecast.get("status") == "success"
        and approve["strategy"]["status"] == "approved",
    }
    write_json(args.evidence, result)
    print(json.dumps(result, ensure_ascii=False, default=str))
    if not result["pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

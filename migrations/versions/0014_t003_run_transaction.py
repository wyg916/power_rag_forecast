"""add T003 forecast run identity and atomic transaction constraints

Revision ID: 0014_t003_run_transaction
Revises: 0013_t001_model_fact
Create Date: 2026-07-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0014_t003_run_transaction"
down_revision = "0013_t001_model_fact"
branch_labels = None
depends_on = None


_RUN_COLUMNS = (
    sa.Column("domain", sa.String(length=64), nullable=True),
    sa.Column("target_name", sa.String(length=128), nullable=True),
    sa.Column("forecast_start_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("forecast_end_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("input_start_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("input_end_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("model_id", sa.String(length=128), nullable=True),
    sa.Column("model_version", sa.String(length=128), nullable=True),
    sa.Column("artifact_id", sa.String(length=128), nullable=True),
    sa.Column("artifact_hash", sa.String(length=128), nullable=True),
    sa.Column("feature_version", sa.String(length=128), nullable=True),
    sa.Column("schema_hash", sa.String(length=128), nullable=True),
    sa.Column("input_hash", sa.String(length=64), nullable=True),
    sa.Column("result_hash", sa.String(length=64), nullable=True),
    sa.Column("source_type", sa.String(length=32), nullable=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("error_code", sa.String(length=64), nullable=True),
    sa.Column("error_message", sa.Text(), nullable=True),
    sa.Column("retry_of_run_id", sa.String(length=64), nullable=True),
    sa.Column("environment_hash", sa.String(length=64), nullable=True),
    sa.Column("record_count", sa.Integer(), nullable=True),
)

_RESULT_COLUMNS = (
    sa.Column("forecast_time", sa.DateTime(timezone=True), nullable=True),
    sa.Column("model_version", sa.String(length=128), nullable=True),
    sa.Column("feature_version", sa.String(length=128), nullable=True),
    sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("base_prediction", sa.Float(), nullable=True),
    sa.Column("peak_prediction", sa.Float(), nullable=True),
    sa.Column("classifier_prediction", sa.Float(), nullable=True),
    sa.Column("p90_prediction", sa.Float(), nullable=True),
    sa.Column("blend_weight", sa.Float(), nullable=True),
    sa.Column("adjustment", sa.Float(), nullable=True),
    sa.Column("component_outputs", sa.JSON(), nullable=True),
    sa.Column("source_type", sa.String(length=32), nullable=True),
)


def _columns(table: str) -> set[str]:
    return {str(item["name"]) for item in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {str(item["name"]) for item in sa.inspect(op.get_bind()).get_indexes(table)}


def _foreign_keys(table: str) -> dict[str, dict]:
    return {
        str(item["name"]): item
        for item in sa.inspect(op.get_bind()).get_foreign_keys(table)
        if item.get("name")
    }


def upgrade() -> None:
    run_columns = _columns("forecast_runs")
    for column in _RUN_COLUMNS:
        if column.name not in run_columns:
            op.add_column("forecast_runs", column)

    result_columns = _columns("forecast_results")
    for column in _RESULT_COLUMNS:
        if column.name not in result_columns:
            op.add_column("forecast_results", column)

    run_indexes = _indexes("forecast_runs")
    if "idx_forecast_runs_latest_success_t003" not in run_indexes:
        op.create_index(
            "idx_forecast_runs_latest_success_t003",
            "forecast_runs",
            ["status", "finished_at", "created_at"],
            unique=False,
        )
    if "idx_forecast_runs_identity_t003" not in run_indexes:
        op.create_index(
            "idx_forecast_runs_identity_t003",
            "forecast_runs",
            ["domain", "target_name", "model_version"],
            unique=False,
        )

    result_indexes = _indexes("forecast_results")
    if "uq_forecast_results_run_time_t003" not in result_indexes:
        op.create_index(
            "uq_forecast_results_run_time_t003",
            "forecast_results",
            ["run_id", "forecast_time"],
            unique=True,
            postgresql_where=sa.text("forecast_time IS NOT NULL"),
        )

    foreign_keys = _foreign_keys("forecast_results")
    for name, definition in foreign_keys.items():
        if (
            definition.get("referred_table") == "forecast_runs"
            and definition.get("constrained_columns") == ["run_id"]
        ):
            op.drop_constraint(name, "forecast_results", type_="foreignkey")
    op.create_foreign_key(
        "fk_forecast_results_run_id_t003",
        "forecast_results",
        "forecast_runs",
        ["run_id"],
        ["run_id"],
        ondelete="RESTRICT",
    )

    run_foreign_keys = _foreign_keys("forecast_runs")
    if "fk_forecast_runs_retry_of_t003" not in run_foreign_keys:
        op.create_foreign_key(
            "fk_forecast_runs_retry_of_t003",
            "forecast_runs",
            "forecast_runs",
            ["retry_of_run_id"],
            ["run_id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    run_foreign_keys = _foreign_keys("forecast_runs")
    if "fk_forecast_runs_retry_of_t003" in run_foreign_keys:
        op.drop_constraint("fk_forecast_runs_retry_of_t003", "forecast_runs", type_="foreignkey")

    result_foreign_keys = _foreign_keys("forecast_results")
    if "fk_forecast_results_run_id_t003" in result_foreign_keys:
        op.drop_constraint("fk_forecast_results_run_id_t003", "forecast_results", type_="foreignkey")
    remaining = _foreign_keys("forecast_results")
    if not any(
        item.get("referred_table") == "forecast_runs"
        and item.get("constrained_columns") == ["run_id"]
        for item in remaining.values()
    ):
        op.create_foreign_key(
            "forecast_results_run_id_fkey",
            "forecast_results",
            "forecast_runs",
            ["run_id"],
            ["run_id"],
            ondelete="CASCADE",
        )

    result_indexes = _indexes("forecast_results")
    if "uq_forecast_results_run_time_t003" in result_indexes:
        op.drop_index("uq_forecast_results_run_time_t003", table_name="forecast_results")

    run_indexes = _indexes("forecast_runs")
    for name in ("idx_forecast_runs_identity_t003", "idx_forecast_runs_latest_success_t003"):
        if name in run_indexes:
            op.drop_index(name, table_name="forecast_runs")

    # Non-destructive downgrade: identity columns are intentionally retained so
    # historical run metadata and results are never discarded.

"""add Day 6 operational input batches and runtime lineage

Revision ID: 0017_day6_operational
Revises: 0016_strategy_runtime
Create Date: 2026-08-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0017_day6_operational"
down_revision = "0016_strategy_runtime"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {str(item["name"]) for item in sa.inspect(op.get_bind()).get_columns(table)}


def _foreign_keys(table: str) -> set[str]:
    return {
        str(item["name"])
        for item in sa.inspect(op.get_bind()).get_foreign_keys(table)
        if item.get("name")
    }


def upgrade() -> None:
    op.create_table(
        "forecast_input_batches",
        sa.Column("batch_id", sa.String(96), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("anchor_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_cutoff_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("source_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_hashes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("feature_version", sa.String(128), nullable=False),
        sa.Column("schema_hash", sa.String(64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("continuity_status", sa.String(32), nullable=False),
        sa.Column("quality_status", sa.String(32), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False, server_default="development_demo"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("idempotency_key", name="uq_forecast_input_batches_idempotency_d6"),
        sa.UniqueConstraint("run_id", name="uq_forecast_input_batches_run_d6"),
        sa.CheckConstraint("row_count = 24", name="ck_forecast_input_batches_rows_d6"),
        sa.CheckConstraint("forecast_end > forecast_start", name="ck_forecast_input_batches_window_d6"),
        sa.CheckConstraint("continuity_status IN ('complete','failed')", name="ck_forecast_input_batches_continuity_d6"),
        sa.CheckConstraint("quality_status IN ('ready','running','success','failed')", name="ck_forecast_input_batches_quality_d6"),
    )
    op.create_index("idx_forecast_input_batches_anchor_d6", "forecast_input_batches", ["anchor_time", "created_at"])
    op.create_index("idx_forecast_input_batches_quality_d6", "forecast_input_batches", ["quality_status", "created_at"])

    op.create_table(
        "forecast_input_snapshots",
        sa.Column("snapshot_id", sa.String(128), primary_key=True),
        sa.Column("batch_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("forecast_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_position_count", sa.Integer(), nullable=False),
        sa.Column("feature_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("feature_hash", sa.String(64), nullable=False),
        sa.Column("source_status", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["batch_id"], ["forecast_input_batches.batch_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("batch_id", "forecast_time", name="uq_forecast_input_snapshots_batch_time_d6"),
        sa.CheckConstraint("feature_position_count > 0", name="ck_forecast_input_snapshots_features_d6"),
    )
    op.create_index("idx_forecast_input_snapshots_run_d6", "forecast_input_snapshots", ["run_id", "forecast_time"])

    run_columns = _columns("forecast_runs")
    for column in (
        sa.Column("input_batch_id", sa.String(96), nullable=True),
        sa.Column("source_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("freshness_status", sa.String(32), nullable=True),
        sa.Column("development_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
    ):
        if column.name not in run_columns:
            op.add_column("forecast_runs", column)
    if "fk_forecast_runs_input_batch_d6" not in _foreign_keys("forecast_runs"):
        op.create_foreign_key(
            "fk_forecast_runs_input_batch_d6",
            "forecast_runs",
            "forecast_input_batches",
            ["input_batch_id"],
            ["batch_id"],
            ondelete="RESTRICT",
        )
    op.create_index("idx_forecast_runs_input_batch_d6", "forecast_runs", ["input_batch_id"], unique=False)

    result_columns = _columns("forecast_results")
    if "input_batch_id" not in result_columns:
        op.add_column("forecast_results", sa.Column("input_batch_id", sa.String(96), nullable=True))
    if "fk_forecast_results_input_batch_d6" not in _foreign_keys("forecast_results"):
        op.create_foreign_key(
            "fk_forecast_results_input_batch_d6",
            "forecast_results",
            "forecast_input_batches",
            ["input_batch_id"],
            ["batch_id"],
            ondelete="RESTRICT",
        )
    op.create_index("idx_forecast_results_input_batch_d6", "forecast_results", ["input_batch_id"], unique=False)


def downgrade() -> None:
    if "fk_forecast_results_input_batch_d6" in _foreign_keys("forecast_results"):
        op.drop_constraint("fk_forecast_results_input_batch_d6", "forecast_results", type_="foreignkey")
    indexes = {str(item["name"]) for item in sa.inspect(op.get_bind()).get_indexes("forecast_results")}
    if "idx_forecast_results_input_batch_d6" in indexes:
        op.drop_index("idx_forecast_results_input_batch_d6", table_name="forecast_results")
    if "input_batch_id" in _columns("forecast_results"):
        op.drop_column("forecast_results", "input_batch_id")

    if "fk_forecast_runs_input_batch_d6" in _foreign_keys("forecast_runs"):
        op.drop_constraint("fk_forecast_runs_input_batch_d6", "forecast_runs", type_="foreignkey")
    indexes = {str(item["name"]) for item in sa.inspect(op.get_bind()).get_indexes("forecast_runs")}
    if "idx_forecast_runs_input_batch_d6" in indexes:
        op.drop_index("idx_forecast_runs_input_batch_d6", table_name="forecast_runs")
    run_columns = _columns("forecast_runs")
    for name in ("development_mode", "freshness_status", "source_metadata_json", "input_batch_id"):
        if name in run_columns:
            op.drop_column("forecast_runs", name)

    op.drop_table("forecast_input_snapshots")
    op.drop_table("forecast_input_batches")

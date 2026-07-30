"""add P6 strategy runtime device, SOC and execution facts

Revision ID: 0016_strategy_runtime
Revises: 0015_phase5d_strategy
Create Date: 2026-07-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0016_strategy_runtime"
down_revision = "0015_phase5d_strategy"
branch_labels = None
depends_on = None


def _source_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("data_source", sa.String(64), nullable=False),
        sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("batch_id", sa.String(96), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scenario", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def upgrade() -> None:
    op.create_table(
        "storage_devices",
        sa.Column("device_id", sa.String(64), primary_key=True),
        sa.Column("device_name", sa.String(128), nullable=False),
        sa.Column("station_name", sa.String(128), nullable=False),
        sa.Column("region", sa.String(64), nullable=False),
        sa.Column("rated_capacity_mwh", sa.Numeric(12, 3), nullable=False),
        sa.Column("rated_power_mw", sa.Numeric(12, 3), nullable=False),
        sa.Column("charge_efficiency", sa.Numeric(6, 4), nullable=False),
        sa.Column("discharge_efficiency", sa.Numeric(6, 4), nullable=False),
        sa.Column("soc_lower_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("soc_upper_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("operating_status", sa.String(32), nullable=False),
        *_source_columns(),
        sa.CheckConstraint("rated_capacity_mwh > 0", name="ck_storage_devices_capacity_p6"),
        sa.CheckConstraint("rated_power_mw > 0", name="ck_storage_devices_power_p6"),
        sa.CheckConstraint(
            "charge_efficiency > 0 AND charge_efficiency <= 1 AND discharge_efficiency > 0 AND discharge_efficiency <= 1",
            name="ck_storage_devices_efficiency_p6",
        ),
        sa.CheckConstraint(
            "soc_lower_pct >= 0 AND soc_upper_pct <= 100 AND soc_lower_pct < soc_upper_pct",
            name="ck_storage_devices_soc_bounds_p6",
        ),
        sa.CheckConstraint(
            "operating_status IN ('online','standby','maintenance','offline')",
            name="ck_storage_devices_status_p6",
        ),
    )
    op.create_index("idx_storage_devices_region_status_p6", "storage_devices", ["region", "operating_status"])
    op.create_index("idx_storage_devices_batch_p6", "storage_devices", ["batch_id", "is_simulated"])

    op.create_table(
        "storage_soc_snapshots",
        sa.Column("snapshot_id", sa.String(96), primary_key=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("soc_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("available_energy_mwh", sa.Numeric(12, 3), nullable=False),
        sa.Column("active_power_mw", sa.Numeric(12, 3), nullable=False),
        sa.Column("operating_mode", sa.String(32), nullable=False),
        *_source_columns(),
        sa.ForeignKeyConstraint(["device_id"], ["storage_devices.device_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("device_id", "observed_at", "batch_id", name="uq_storage_soc_device_time_batch_p6"),
        sa.CheckConstraint("soc_pct >= 0 AND soc_pct <= 100", name="ck_storage_soc_pct_p6"),
        sa.CheckConstraint("available_energy_mwh >= 0", name="ck_storage_soc_energy_p6"),
        sa.CheckConstraint(
            "operating_mode IN ('charging','discharging','idle','standby')",
            name="ck_storage_soc_mode_p6",
        ),
    )
    op.create_index("idx_storage_soc_latest_p6", "storage_soc_snapshots", ["device_id", "observed_at"])
    op.create_index("idx_storage_soc_batch_p6", "storage_soc_snapshots", ["batch_id", "is_simulated"])

    op.create_table(
        "strategy_execution_items",
        sa.Column("execution_id", sa.String(96), primary_key=True),
        sa.Column("strategy_id", sa.String(96), nullable=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("window_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("planned_power_mw", sa.Numeric(12, 3), nullable=False),
        sa.Column("actual_power_mw", sa.Numeric(12, 3), nullable=True),
        sa.Column("planned_energy_mwh", sa.Numeric(12, 3), nullable=False),
        sa.Column("actual_energy_mwh", sa.Numeric(12, 3), nullable=True),
        sa.Column("soc_before_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("soc_after_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("execution_status", sa.String(32), nullable=False),
        sa.Column("feedback_message", sa.Text(), nullable=True),
        sa.Column("realized_revenue_cny", sa.Numeric(16, 2), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
        sa.Column("settlement_method", sa.String(64), nullable=False),
        *_source_columns(),
        sa.ForeignKeyConstraint(["device_id"], ["storage_devices.device_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("window_end_at > window_start_at", name="ck_strategy_execution_window_p6"),
        sa.CheckConstraint("action IN ('charge','discharge','standby')", name="ck_strategy_execution_action_p6"),
        sa.CheckConstraint(
            "execution_status IN ('scheduled','in_progress','completed','partial','failed','cancelled')",
            name="ck_strategy_execution_status_p6",
        ),
        sa.CheckConstraint("planned_power_mw >= 0 AND planned_energy_mwh >= 0", name="ck_strategy_execution_plan_p6"),
        sa.CheckConstraint(
            "soc_before_pct >= 0 AND soc_before_pct <= 100 AND (soc_after_pct IS NULL OR (soc_after_pct >= 0 AND soc_after_pct <= 100))",
            name="ck_strategy_execution_soc_p6",
        ),
    )
    op.create_index("idx_strategy_execution_device_time_p6", "strategy_execution_items", ["device_id", "window_start_at"])
    op.create_index("idx_strategy_execution_status_p6", "strategy_execution_items", ["execution_status", "window_start_at"])
    op.create_index("idx_strategy_execution_batch_p6", "strategy_execution_items", ["batch_id", "is_simulated"])


def downgrade() -> None:
    op.drop_table("strategy_execution_items")
    op.drop_table("storage_soc_snapshots")
    op.drop_table("storage_devices")

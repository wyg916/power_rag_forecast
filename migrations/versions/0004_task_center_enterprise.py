"""extend task center enterprise fields

Revision ID: 0004_task_center_enterprise
Revises: 0003_stage1_raw_data
Create Date: 2026-06-08
"""
from __future__ import annotations

from alembic import op


revision = "0004_task_center_enterprise"
down_revision = "0003_stage1_raw_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE task_runs
            ADD COLUMN IF NOT EXISTS task_type VARCHAR(64),
            ADD COLUMN IF NOT EXISTS progress DOUBLE PRECISION NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS message TEXT,
            ADD COLUMN IF NOT EXISTS created_by VARCHAR(128),
            ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS result_ref TEXT,
            ADD COLUMN IF NOT EXISTS metadata_json JSONB,
            ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP
        """
    )
    op.execute(
        """
        ALTER TABLE task_logs
            ADD COLUMN IF NOT EXISTS progress DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS message TEXT,
            ADD COLUMN IF NOT EXISTS result_ref TEXT,
            ADD COLUMN IF NOT EXISTS metadata_json JSONB
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_kind ON task_runs(task_kind)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_created_by ON task_runs(created_by)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_created_at ON task_runs(created_at)")


def downgrade() -> None:
    # Productization migrations are intentionally non-destructive in this phase.
    pass

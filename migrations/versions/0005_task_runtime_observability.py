"""add task runtime observability fields

Revision ID: 0005_task_runtime_observability
Revises: 0004_task_center_enterprise
Create Date: 2026-06-08
"""
from __future__ import annotations

from alembic import op


revision = "0005_task_runtime_observability"
down_revision = "0004_task_center_enterprise"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE task_runs
            ADD COLUMN IF NOT EXISTS execution_mode VARCHAR(32),
            ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS worker_id VARCHAR(128),
            ADD COLUMN IF NOT EXISTS celery_task_id VARCHAR(128)
        """
    )
    op.execute(
        """
        ALTER TABLE task_logs
            ADD COLUMN IF NOT EXISTS execution_mode VARCHAR(32),
            ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN,
            ADD COLUMN IF NOT EXISTS worker_id VARCHAR(128),
            ADD COLUMN IF NOT EXISTS celery_task_id VARCHAR(128)
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_execution_mode ON task_runs(execution_mode)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_cancel_requested ON task_runs(cancel_requested)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_worker_id ON task_runs(worker_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_celery_task_id ON task_runs(celery_task_id)")


def downgrade() -> None:
    # Productization migrations are intentionally non-destructive in this phase.
    pass

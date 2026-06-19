"""productionize task runtime fields

Revision ID: 0007_task_runtime
Revises: 0006_auth_users
Create Date: 2026-06-19
"""
from __future__ import annotations

from alembic import op


revision = "0007_task_runtime"
down_revision = "0006_auth_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE task_runs
            ADD COLUMN IF NOT EXISTS queued_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS error_code VARCHAR(64),
            ADD COLUMN IF NOT EXISTS error_detail TEXT,
            ADD COLUMN IF NOT EXISTS cancel_reason TEXT,
            ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS timeout_seconds INTEGER,
            ADD COLUMN IF NOT EXISTS timeout_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS max_retries INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS parent_task_id VARCHAR(64),
            ADD COLUMN IF NOT EXISTS original_task_id VARCHAR(64),
            ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(256),
            ADD COLUMN IF NOT EXISTS payload_hash VARCHAR(64),
            ADD COLUMN IF NOT EXISTS dedupe_window_seconds INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS queue_name VARCHAR(64)
        """
    )
    op.execute(
        """
        ALTER TABLE task_logs
            ADD COLUMN IF NOT EXISTS level VARCHAR(16),
            ADD COLUMN IF NOT EXISTS step VARCHAR(32),
            ADD COLUMN IF NOT EXISTS sequence_no INTEGER
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_queue_name ON task_runs(queue_name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_idempotency_key ON task_runs(idempotency_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_payload_hash ON task_runs(payload_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_parent_task_id ON task_runs(parent_task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_timeout_at ON task_runs(timeout_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_logs_task_step ON task_logs(task_id, step)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_logs_level ON task_logs(level)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_logs_created_at ON task_logs(created_at)")


def downgrade() -> None:
    # Productization migrations are intentionally non-destructive in this phase.
    pass

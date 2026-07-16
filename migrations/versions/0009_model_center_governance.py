"""model center governance events

Revision ID: 0009_model_center_governance
Revises: 0008_knowledge_business
Create Date: 2026-06-30
"""
from __future__ import annotations

from alembic import op


revision = "0009_model_center_governance"
down_revision = "0008_knowledge_business"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_governance_events (
            id SERIAL PRIMARY KEY,
            event_id VARCHAR(64) NOT NULL UNIQUE,
            action VARCHAR(64) NOT NULL,
            target_version VARCHAR(128),
            source_version VARCHAR(128),
            operator VARCHAR(128),
            reason TEXT,
            status VARCHAR(32) NOT NULL DEFAULT 'success',
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_governance_events_action ON model_governance_events(action)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_governance_events_created ON model_governance_events(created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_governance_events_target ON model_governance_events(target_version)")


def downgrade() -> None:
    # Productization migrations are intentionally non-destructive in this phase.
    pass

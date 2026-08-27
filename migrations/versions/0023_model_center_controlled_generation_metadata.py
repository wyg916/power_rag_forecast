"""add controlled-generation audit metadata to model registry

Revision ID: 0023_model_center_facts
Revises: 0022_chatbi_semantic_v1
Create Date: 2026-08-27
"""
from __future__ import annotations

from alembic import op


revision = "0023_model_center_facts"
down_revision = "0022_chatbi_semantic_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE model_registry
        ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_model_registry_controlled_batch
        ON model_registry ((metadata_json ->> 'batch_id'))
        WHERE metadata_json ? 'batch_id'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_model_registry_controlled_batch")
    op.execute("ALTER TABLE model_registry DROP COLUMN IF EXISTS metadata_json")

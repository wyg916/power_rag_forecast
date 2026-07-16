"""knowledge page business closure tables

Revision ID: 0008_knowledge_business
Revises: 0007_task_runtime
Create Date: 2026-06-30
"""
from __future__ import annotations

from alembic import op


revision = "0008_knowledge_business"
down_revision = "0007_task_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS kb_search_results (
            id SERIAL PRIMARY KEY,
            search_id VARCHAR(64) NOT NULL UNIQUE,
            query_text TEXT NOT NULL,
            top_k INTEGER NOT NULL DEFAULT 5,
            result_count INTEGER NOT NULL DEFAULT 0,
            items_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            retrieval_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            timings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS kb_qa_tests (
            id SERIAL PRIMARY KEY,
            test_id VARCHAR(64) NOT NULL UNIQUE,
            question TEXT NOT NULL,
            top_k INTEGER NOT NULL DEFAULT 5,
            answer TEXT NOT NULL DEFAULT '',
            answer_blocks_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            result_count INTEGER NOT NULL DEFAULT 0,
            passed BOOLEAN NOT NULL DEFAULT FALSE,
            confidence NUMERIC(6,2) NOT NULL DEFAULT 0,
            latency_ms NUMERIC(12,3) NOT NULL DEFAULT 0,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_kb_search_results_created_at ON kb_search_results(created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_kb_search_results_query ON kb_search_results USING GIN (to_tsvector('simple', query_text))")
    op.execute("CREATE INDEX IF NOT EXISTS idx_kb_qa_tests_created_at ON kb_qa_tests(created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_kb_qa_tests_passed ON kb_qa_tests(passed)")


def downgrade() -> None:
    # Productization migrations are intentionally non-destructive in this phase.
    pass

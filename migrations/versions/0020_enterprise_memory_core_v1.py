"""enterprise long-term memory core v1

Revision ID: 0020_enterprise_memory_core_v1
Revises: 0019_memory_identity_safety
Create Date: 2026-08-10
"""
from __future__ import annotations

from alembic import op


revision = "0020_enterprise_memory_core_v1"
down_revision = "0019_memory_identity_safety"
branch_labels = None
depends_on = None


MEMORY_TABLES = (
    "ai_memory_records",
    "ai_memory_versions",
    "ai_memory_relations",
    "ai_memory_usage",
    "ai_memory_outbox",
    "ai_memory_admissions",
    "ai_memory_state_transitions",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ai_memory_records (
            memory_id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL,
            workspace_id VARCHAR(64) NOT NULL,
            user_id VARCHAR(128) NOT NULL,
            agent_id VARCHAR(64) NOT NULL,
            memory_type VARCHAR(24) NOT NULL,
            subject_type VARCHAR(24) NOT NULL,
            content TEXT NOT NULL,
            summary TEXT NOT NULL,
            source_type VARCHAR(48) NOT NULL,
            source_id VARCHAR(160),
            confidence NUMERIC(5,4) NOT NULL,
            importance NUMERIC(5,4) NOT NULL,
            status VARCHAR(24) NOT NULL,
            session_id VARCHAR(128),
            run_id VARCHAR(128),
            occurred_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMPTZ,
            current_version INTEGER NOT NULL DEFAULT 1,
            content_hash CHAR(64) NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT ck_ai_memory_type CHECK (memory_type IN ('semantic', 'episodic', 'procedural')),
            CONSTRAINT ck_ai_memory_subject CHECK (subject_type IN ('user_fact', 'business_fact', 'system_fact', 'task_episode')),
            CONSTRAINT ck_ai_memory_status CHECK (status IN ('draft', 'pending', 'active', 'cold', 'archived', 'deleted')),
            CONSTRAINT ck_ai_memory_confidence CHECK (confidence >= 0 AND confidence <= 1),
            CONSTRAINT ck_ai_memory_importance CHECK (importance >= 0 AND importance <= 1),
            CONSTRAINT ck_ai_memory_version CHECK (current_version >= 1),
            CONSTRAINT ck_ai_memory_expiry CHECK (expires_at IS NULL OR expires_at > created_at),
            CONSTRAINT ck_ai_memory_episode_scope CHECK (
                memory_type <> 'episodic'
                OR (session_id IS NOT NULL AND run_id IS NOT NULL AND occurred_at IS NOT NULL)
            )
        );

        CREATE INDEX idx_ai_memory_scope_retrieval
          ON ai_memory_records(
            tenant_id, workspace_id, user_id, agent_id,
            status, memory_type, importance DESC, updated_at DESC
          );
        CREATE UNIQUE INDEX uq_ai_memory_scope_hash
          ON ai_memory_records(tenant_id, workspace_id, user_id, agent_id, content_hash)
          WHERE status <> 'deleted';
        CREATE INDEX idx_ai_memory_expires
          ON ai_memory_records(expires_at) WHERE expires_at IS NOT NULL;
        CREATE INDEX idx_ai_memory_fulltext
          ON ai_memory_records USING GIN (to_tsvector('simple', summary || ' ' || content));
        CREATE INDEX idx_ai_memory_source
          ON ai_memory_records(tenant_id, workspace_id, user_id, agent_id, source_type, source_id)
          WHERE source_id IS NOT NULL AND status <> 'deleted';

        CREATE TABLE ai_memory_versions (
            version_id VARCHAR(72) PRIMARY KEY,
            memory_id VARCHAR(64) NOT NULL REFERENCES ai_memory_records(memory_id),
            version_no INTEGER NOT NULL,
            content TEXT NOT NULL,
            summary TEXT NOT NULL,
            content_hash CHAR(64) NOT NULL,
            source JSONB NOT NULL DEFAULT '{}'::jsonb,
            confidence NUMERIC(5,4) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            supersedes_version_id VARCHAR(72) REFERENCES ai_memory_versions(version_id),
            created_by_run_id VARCHAR(128) NOT NULL,
            change_reason TEXT NOT NULL,
            CONSTRAINT uq_ai_memory_version UNIQUE(memory_id, version_no),
            CONSTRAINT ck_ai_memory_version_no CHECK (version_no >= 1),
            CONSTRAINT ck_ai_memory_version_confidence CHECK (confidence >= 0 AND confidence <= 1)
        );
        CREATE INDEX idx_ai_memory_versions_history
          ON ai_memory_versions(memory_id, version_no DESC, created_at DESC);

        CREATE TABLE ai_memory_relations (
            relation_id VARCHAR(72) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL,
            workspace_id VARCHAR(64) NOT NULL,
            user_id VARCHAR(128) NOT NULL,
            agent_id VARCHAR(64) NOT NULL,
            source_memory_id VARCHAR(64) NOT NULL REFERENCES ai_memory_records(memory_id),
            target_memory_id VARCHAR(64) NOT NULL REFERENCES ai_memory_records(memory_id),
            relation_type VARCHAR(24) NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            created_by_run_id VARCHAR(128) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_ai_memory_relation_type CHECK (
                relation_type IN ('SUPPORTS', 'CONTRADICTS', 'SUPERSEDES', 'DERIVED_FROM', 'RELATED_TO')
            ),
            CONSTRAINT ck_ai_memory_relation_self CHECK (source_memory_id <> target_memory_id),
            CONSTRAINT uq_ai_memory_relation UNIQUE(source_memory_id, target_memory_id, relation_type)
        );
        CREATE INDEX idx_ai_memory_relations_scope
          ON ai_memory_relations(tenant_id, workspace_id, user_id, agent_id, source_memory_id);

        CREATE TABLE ai_memory_usage (
            usage_id VARCHAR(72) PRIMARY KEY,
            memory_id VARCHAR(64) NOT NULL REFERENCES ai_memory_records(memory_id),
            version_id VARCHAR(72) NOT NULL REFERENCES ai_memory_versions(version_id),
            tenant_id VARCHAR(64) NOT NULL,
            workspace_id VARCHAR(64) NOT NULL,
            user_id VARCHAR(128) NOT NULL,
            agent_id VARCHAR(64) NOT NULL,
            session_id VARCHAR(128) NOT NULL,
            run_id VARCHAR(128) NOT NULL,
            trace_id VARCHAR(128) NOT NULL,
            usage_type VARCHAR(40) NOT NULL,
            retrieved_at TIMESTAMPTZ NOT NULL,
            used_in_answer BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_ai_memory_usage UNIQUE(trace_id, memory_id, version_id, usage_type)
        );
        CREATE INDEX idx_ai_memory_usage_trace
          ON ai_memory_usage(tenant_id, workspace_id, user_id, agent_id, trace_id, created_at DESC);
        CREATE INDEX idx_ai_memory_usage_memory
          ON ai_memory_usage(memory_id, version_id, created_at DESC);

        CREATE TABLE ai_memory_outbox (
            event_id VARCHAR(72) PRIMARY KEY,
            memory_id VARCHAR(64) NOT NULL REFERENCES ai_memory_records(memory_id),
            tenant_id VARCHAR(64) NOT NULL,
            workspace_id VARCHAR(64) NOT NULL,
            user_id VARCHAR(128) NOT NULL,
            agent_id VARCHAR(64) NOT NULL,
            event_type VARCHAR(40) NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMPTZ,
            last_error TEXT,
            idempotency_key VARCHAR(160) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_ai_memory_event_type CHECK (
                event_type IN ('MEMORY_CREATED', 'MEMORY_UPDATED', 'MEMORY_ARCHIVED', 'MEMORY_DELETE_REQUESTED')
            ),
            CONSTRAINT ck_ai_memory_outbox_status CHECK (status IN ('pending', 'processing', 'processed', 'failed')),
            CONSTRAINT ck_ai_memory_attempts CHECK (attempt_count >= 0),
            CONSTRAINT uq_ai_memory_outbox_key UNIQUE(idempotency_key)
        );
        CREATE INDEX idx_ai_memory_outbox_dispatch
          ON ai_memory_outbox(status, available_at, created_at) WHERE status IN ('pending', 'failed');

        CREATE TABLE ai_memory_admissions (
            admission_id VARCHAR(72) PRIMARY KEY,
            memory_id VARCHAR(64) REFERENCES ai_memory_records(memory_id),
            tenant_id VARCHAR(64) NOT NULL,
            workspace_id VARCHAR(64) NOT NULL,
            user_id VARCHAR(128) NOT NULL,
            agent_id VARCHAR(64) NOT NULL,
            session_id VARCHAR(128),
            run_id VARCHAR(128) NOT NULL,
            memory_type VARCHAR(24) NOT NULL,
            source_type VARCHAR(48) NOT NULL,
            source_id VARCHAR(160),
            candidate_content_hash CHAR(64) NOT NULL,
            confidence NUMERIC(5,4) NOT NULL,
            importance NUMERIC(5,4) NOT NULL,
            business_value NUMERIC(5,4) NOT NULL,
            contains_sensitive BOOLEAN NOT NULL,
            duplicate_memory_id VARCHAR(64),
            conflict_memory_id VARCHAR(64),
            expires_at TIMESTAMPTZ,
            decision VARCHAR(32) NOT NULL,
            reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_ai_memory_admission_decision CHECK (
                decision IN ('REJECT', 'SESSION_ONLY', 'LONG_TERM_CANDIDATE', 'LONG_TERM_ACCEPTED')
            )
        );
        CREATE INDEX idx_ai_memory_admission_scope
          ON ai_memory_admissions(tenant_id, workspace_id, user_id, agent_id, created_at DESC);

        CREATE TABLE ai_memory_state_transitions (
            transition_id VARCHAR(72) PRIMARY KEY,
            memory_id VARCHAR(64) NOT NULL REFERENCES ai_memory_records(memory_id),
            tenant_id VARCHAR(64) NOT NULL,
            workspace_id VARCHAR(64) NOT NULL,
            user_id VARCHAR(128) NOT NULL,
            agent_id VARCHAR(64) NOT NULL,
            from_status VARCHAR(24),
            to_status VARCHAR(24) NOT NULL,
            reason TEXT NOT NULL,
            changed_by_run_id VARCHAR(128) NOT NULL,
            changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_ai_memory_state_history
          ON ai_memory_state_transitions(memory_id, changed_at DESC);
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'beta10d_app_runtime') THEN
                GRANT SELECT, INSERT, UPDATE ON
                    ai_memory_records, ai_memory_versions, ai_memory_relations,
                    ai_memory_usage, ai_memory_outbox, ai_memory_admissions,
                    ai_memory_state_transitions
                TO beta10d_app_runtime;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'beta10d_app_runtime') THEN
                REVOKE ALL PRIVILEGES ON
                    ai_memory_records, ai_memory_versions, ai_memory_relations,
                    ai_memory_usage, ai_memory_outbox, ai_memory_admissions,
                    ai_memory_state_transitions
                FROM beta10d_app_runtime;
            END IF;
        END $$
        """
    )
    for table in reversed(MEMORY_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")

"""scope assistant memory and traces by authoritative identity

Revision ID: 0019_memory_identity_safety
Revises: 0018_rag_enterprise_r1
Create Date: 2026-08-08
"""
from __future__ import annotations

from alembic import op


revision = "0019_memory_identity_safety"
down_revision = "0018_rag_enterprise_r1"
branch_labels = None
depends_on = None


MEMORY_TABLES = (
    "ai_chat_sessions",
    "ai_chat_messages",
    "ai_conversation_state",
    "ai_tool_call_logs",
    "ai_chat_feedback",
    "ai_answer_feedback",
    "ai_traces",
)


def _add_identity_columns(table: str) -> None:
    op.execute(
        f"""
        ALTER TABLE {table}
            ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) NOT NULL DEFAULT 'default',
            ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64) NOT NULL DEFAULT 'default',
            ADD COLUMN IF NOT EXISTS user_id VARCHAR(128) NOT NULL DEFAULT 'legacy_unowned',
            ADD COLUMN IF NOT EXISTS role_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS agent_id VARCHAR(64) NOT NULL DEFAULT 'ai_assistant',
            ADD COLUMN IF NOT EXISTS run_id VARCHAR(128)
        """
    )
    op.execute(f"ALTER TABLE {table} ALTER COLUMN user_id DROP DEFAULT")


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) NOT NULL DEFAULT 'default',
            ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64) NOT NULL DEFAULT 'default'
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'beta10d_app_runtime') THEN
                GRANT DELETE ON ai_chat_sessions, ai_chat_messages, ai_conversation_state,
                    ai_tool_call_logs, ai_chat_feedback, ai_answer_feedback, ai_traces
                TO beta10d_app_runtime;
            END IF;
        END $$
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_tenant_workspace ON users(tenant_id, workspace_id, user_id)")

    for table in MEMORY_TABLES:
        _add_identity_columns(table)

    op.execute(
        """
        UPDATE ai_chat_sessions
        SET user_id = COALESCE(NULLIF(user_id, ''), 'legacy_unowned')
        """
    )
    op.execute(
        """
        ALTER TABLE ai_chat_messages ADD COLUMN IF NOT EXISTS message_key VARCHAR(160);
        ALTER TABLE ai_tool_call_logs ADD COLUMN IF NOT EXISTS tool_call_key VARCHAR(160);
        ALTER TABLE ai_chat_feedback ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(160);
        ALTER TABLE ai_answer_feedback ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(160)
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_chat_sessions_identity
          ON ai_chat_sessions(tenant_id, workspace_id, user_id, agent_id, session_id);
        CREATE INDEX IF NOT EXISTS idx_ai_chat_sessions_identity_updated
          ON ai_chat_sessions(tenant_id, workspace_id, user_id, agent_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_ai_conversation_state_identity
          ON ai_conversation_state(tenant_id, workspace_id, user_id, agent_id, session_id);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_chat_messages_idempotency
          ON ai_chat_messages(tenant_id, workspace_id, user_id, agent_id, session_id, message_key)
          WHERE message_key IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_tool_calls_idempotency
          ON ai_tool_call_logs(tenant_id, workspace_id, user_id, agent_id, session_id, tool_call_key)
          WHERE tool_call_key IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_chat_feedback_idempotency
          ON ai_chat_feedback(tenant_id, workspace_id, user_id, agent_id, idempotency_key)
          WHERE idempotency_key IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_answer_feedback_idempotency
          ON ai_answer_feedback(tenant_id, workspace_id, user_id, agent_id, idempotency_key)
          WHERE idempotency_key IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_ai_traces_identity_created
          ON ai_traces(tenant_id, workspace_id, user_id, agent_id, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'beta10d_app_runtime') THEN
                REVOKE DELETE ON ai_chat_sessions, ai_chat_messages, ai_conversation_state,
                    ai_tool_call_logs, ai_chat_feedback, ai_answer_feedback, ai_traces
                FROM beta10d_app_runtime;
            END IF;
        END $$
        """
    )
    for index in (
        "idx_ai_traces_identity_created",
        "uq_ai_answer_feedback_idempotency",
        "uq_ai_chat_feedback_idempotency",
        "uq_ai_tool_calls_idempotency",
        "uq_ai_chat_messages_idempotency",
        "idx_ai_conversation_state_identity",
        "idx_ai_chat_sessions_identity_updated",
        "idx_ai_chat_sessions_identity",
    ):
        op.execute(f"DROP INDEX IF EXISTS {index}")

    op.execute("ALTER TABLE ai_answer_feedback DROP COLUMN IF EXISTS idempotency_key")
    op.execute("ALTER TABLE ai_chat_feedback DROP COLUMN IF EXISTS idempotency_key")
    op.execute("ALTER TABLE ai_tool_call_logs DROP COLUMN IF EXISTS tool_call_key")
    op.execute("ALTER TABLE ai_chat_messages DROP COLUMN IF EXISTS message_key")

    for table in reversed(MEMORY_TABLES):
        for column in ("run_id", "agent_id", "role_ids", "workspace_id", "tenant_id"):
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}")
        if table != "ai_chat_sessions":
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS user_id")

    op.execute("DROP INDEX IF EXISTS idx_users_tenant_workspace")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS workspace_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS tenant_id")

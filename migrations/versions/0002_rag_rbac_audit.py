"""add basic RAG, RBAC and audit tables

Revision ID: 0002_rag_rbac_audit
Revises: 0001_initial_postgres_schema
Create Date: 2026-06-01
"""
from __future__ import annotations

from alembic import op


revision = "0002_rag_rbac_audit"
down_revision = "0001_initial_postgres_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            CREATE EXTENSION IF NOT EXISTS vector;
        EXCEPTION WHEN others THEN
            NULL;
        END $$;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS kb_documents (
            doc_id VARCHAR(64) PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            source_type VARCHAR(64) NOT NULL DEFAULT 'local_file',
            source_path TEXT,
            checksum VARCHAR(128),
            metadata_json JSONB,
            indexed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS kb_chunks (
            chunk_id VARCHAR(96) PRIMARY KEY,
            doc_id VARCHAR(64) NOT NULL REFERENCES kb_documents(doc_id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            keywords_json JSONB,
            embedding_json JSONB,
            metadata_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uk_kb_doc_chunk UNIQUE (doc_id, chunk_index)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_kb_chunks_doc_id ON kb_chunks(doc_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_kb_documents_source ON kb_documents(source_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_kb_chunks_keywords_gin ON kb_chunks USING GIN (keywords_json)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS roles (
            role_id VARCHAR(64) PRIMARY KEY,
            role_name VARCHAR(128) NOT NULL UNIQUE,
            permissions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            description TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id VARCHAR(64) PRIMARY KEY,
            username VARCHAR(128) NOT NULL UNIQUE,
            display_name VARCHAR(128),
            role_id VARCHAR(64) REFERENCES roles(role_id),
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            password_hash TEXT,
            metadata_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_role_id ON users(role_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id BIGSERIAL PRIMARY KEY,
            actor VARCHAR(128),
            role_id VARCHAR(64),
            action VARCHAR(128) NOT NULL,
            resource_type VARCHAR(64),
            resource_id VARCHAR(128),
            status VARCHAR(32) NOT NULL DEFAULT 'success',
            request_id VARCHAR(64),
            ip_address VARCHAR(64),
            metadata_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at)")

    op.execute(
        """
        ALTER TABLE ai_traces
            ADD COLUMN IF NOT EXISTS llm_output_json JSONB,
            ADD COLUMN IF NOT EXISTS rag_context_json JSONB,
            ADD COLUMN IF NOT EXISTS duration_ms INTEGER,
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        """
    )

    op.execute(
        """
        INSERT INTO roles (role_id, role_name, permissions_json, description)
        VALUES
            ('admin', '系统管理员', '["*"]'::jsonb, '默认系统管理员，拥有全部权限'),
            ('operator', '业务运营', '["dashboard:read","forecast:read","forecast:run","data:read","task:read","task:run","assistant:use","knowledge:read","report:read","report:generate"]'::jsonb, '可运行预测、任务、AI 助手和报告生成'),
            ('viewer', '只读用户', '["dashboard:read","forecast:read","data:read","assistant:use","knowledge:read","report:read","model:read","task:read"]'::jsonb, '只读查看和基础 AI 问答')
        ON CONFLICT (role_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO users (user_id, username, display_name, role_id, status, metadata_json)
        VALUES ('dev_admin', 'dev_admin', '本地管理员', 'admin', 'active', '{"source":"migration_seed"}'::jsonb)
        ON CONFLICT (user_id) DO NOTHING
        """
    )


def downgrade() -> None:
    # Productization migrations are non-destructive in this phase.
    pass

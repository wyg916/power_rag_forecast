"""add JWT login user fields

Revision ID: 0006_auth_users
Revises: 0005_task_runtime_observability
Create Date: 2026-06-09
"""
from __future__ import annotations

from alembic import op


revision = "0006_auth_users"
down_revision = "0005_task_runtime_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'id'
            ) THEN
                CREATE SEQUENCE IF NOT EXISTS users_id_seq;
                ALTER TABLE users ADD COLUMN id BIGINT;
                ALTER TABLE users ALTER COLUMN id SET DEFAULT nextval('users_id_seq');
                UPDATE users SET id = nextval('users_id_seq') WHERE id IS NULL;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS email VARCHAR(255),
            ADD COLUMN IF NOT EXISTS role VARCHAR(64),
            ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP
        """
    )
    op.execute("UPDATE users SET role = COALESCE(role, role_id, 'viewer')")
    op.execute("UPDATE users SET role = 'analyst' WHERE role = 'operator'")
    op.execute("UPDATE users SET is_active = FALSE WHERE status IN ('disabled','inactive','locked')")
    op.execute("UPDATE users SET is_superuser = TRUE WHERE role = 'admin'")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_id_unique ON users(id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_roles (
            user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            role_id VARCHAR(64) NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, role_id)
        )
        """
    )

    op.execute(
        """
        INSERT INTO roles (role_id, role_name, permissions_json, description)
        VALUES
            ('analyst', '业务分析员', '["dashboard:read","forecast:read","forecast:run","data:read","data:sync","task:read","task:run","assistant:use","knowledge:read","knowledge:write","report:read","report:generate","report:review","model:read"]'::jsonb, '可执行分析、报告、知识库与普通任务'),
            ('developer', '开发调试员', '["dashboard:read","forecast:read","data:read","task:read","assistant:use","assistant:debug","knowledge:read","report:read","model:read","trace:read","security:read"]'::jsonb, '可查看调试 Trace 和模型路由信息')
        ON CONFLICT (role_id) DO NOTHING
        """
    )
    op.execute("UPDATE users SET role_id = COALESCE(role_id, role)")
    op.execute(
        """
        INSERT INTO user_roles (user_id, role_id)
        SELECT user_id, COALESCE(role, role_id, 'viewer')
        FROM users
        ON CONFLICT (user_id, role_id) DO NOTHING
        """
    )


def downgrade() -> None:
    # Productization migrations are intentionally non-destructive in this phase.
    pass


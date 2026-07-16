"""settings center business closure tables

Revision ID: 0011_settings_center_closure
Revises: 0010_model_pred_points
Create Date: 2026-07-02
"""
from __future__ import annotations

from alembic import op


revision = "0011_settings_center_closure"
down_revision = "0010_model_pred_points"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS system_runtime_config (
            id BIGSERIAL PRIMARY KEY,
            config_key VARCHAR(128) NOT NULL UNIQUE,
            config_value TEXT,
            value_type VARCHAR(32) NOT NULL DEFAULT 'string',
            category VARCHAR(64) NOT NULL DEFAULT 'runtime',
            description TEXT,
            is_sensitive BOOLEAN NOT NULL DEFAULT FALSE,
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            updated_by VARCHAR(128),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_system_runtime_config_category ON system_runtime_config(category)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_system_runtime_config_enabled ON system_runtime_config(is_enabled)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS system_health_snapshots (
            id BIGSERIAL PRIMARY KEY,
            module_key VARCHAR(128) NOT NULL,
            module_name VARCHAR(128) NOT NULL,
            module_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL,
            summary TEXT,
            latency_ms DOUBLE PRECISION,
            qps DOUBLE PRECISION,
            error_rate DOUBLE PRECISION,
            extra_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            checked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source VARCHAR(32) NOT NULL DEFAULT 'runtime'
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_system_health_snapshots_module ON system_health_snapshots(module_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_system_health_snapshots_checked_at ON system_health_snapshots(checked_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_system_health_snapshots_status ON system_health_snapshots(status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS system_api_configs (
            id BIGSERIAL PRIMARY KEY,
            interface_key VARCHAR(128) NOT NULL UNIQUE,
            interface_name VARCHAR(128) NOT NULL,
            interface_type VARCHAR(64) NOT NULL,
            service_url TEXT,
            host VARCHAR(255),
            port INTEGER,
            database_name VARCHAR(128),
            username VARCHAR(128),
            password_encrypted TEXT,
            api_key_encrypted TEXT,
            secret_ref VARCHAR(255),
            health_path VARCHAR(255),
            protocol VARCHAR(32),
            environment VARCHAR(64),
            timeout_seconds INTEGER NOT NULL DEFAULT 5,
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            status VARCHAR(32) NOT NULL DEFAULT 'not_configured',
            last_latency_ms DOUBLE PRECISION,
            success_rate DOUBLE PRECISION,
            last_checked_at TIMESTAMP,
            extra_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_by VARCHAR(128)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_system_api_configs_type ON system_api_configs(interface_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_system_api_configs_status ON system_api_configs(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_system_api_configs_enabled ON system_api_configs(is_enabled)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS system_api_test_logs (
            id BIGSERIAL PRIMARY KEY,
            interface_id BIGINT REFERENCES system_api_configs(id) ON DELETE SET NULL,
            interface_key VARCHAR(128),
            interface_name VARCHAR(128) NOT NULL,
            test_result VARCHAR(32) NOT NULL,
            latency_ms DOUBLE PRECISION,
            error_message TEXT,
            tested_by VARCHAR(128),
            tested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            response_summary TEXT,
            extra_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_system_api_test_logs_interface ON system_api_test_logs(interface_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_system_api_test_logs_tested_at ON system_api_test_logs(tested_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_system_api_test_logs_result ON system_api_test_logs(test_result)")


def downgrade() -> None:
    # Productization migrations are intentionally non-destructive in this phase.
    pass

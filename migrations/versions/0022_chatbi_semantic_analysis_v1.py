"""ChatBI semantic catalog and analysis plan audit v1.

Revision ID: 0022_chatbi_semantic_v1
Revises: 0021_memory_lifecycle_v1
Create Date: 2026-08-11
"""
from __future__ import annotations

from alembic import op


revision = "0022_chatbi_semantic_v1"
down_revision = "0021_memory_lifecycle_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE chatbi_metric_catalog (
          metric_id VARCHAR(64) NOT NULL,
          version INTEGER NOT NULL,
          metric_name VARCHAR(128) NOT NULL,
          business_name VARCHAR(128) NOT NULL,
          description TEXT NOT NULL,
          formula TEXT NOT NULL,
          unit VARCHAR(32) NOT NULL,
          aggregation VARCHAR(32) NOT NULL,
          time_grain JSONB NOT NULL,
          allowed_dimensions JSONB NOT NULL,
          allowed_datasets JSONB NOT NULL,
          allowed_joins JSONB NOT NULL,
          valid_from DATE NOT NULL,
          valid_to DATE,
          status VARCHAR(20) NOT NULL,
          permission VARCHAR(64) NOT NULL,
          definition_hash CHAR(64) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(metric_id, version),
          CONSTRAINT ck_chatbi_metric_status CHECK (status IN ('draft','active','retired'))
        );

        CREATE TABLE chatbi_dimension_catalog (
          dimension_id VARCHAR(64) NOT NULL,
          version INTEGER NOT NULL,
          name VARCHAR(128) NOT NULL,
          business_name VARCHAR(128) NOT NULL,
          dataset VARCHAR(64) NOT NULL,
          field VARCHAR(64) NOT NULL,
          data_type VARCHAR(24) NOT NULL,
          allowed_values JSONB,
          hierarchy JSONB NOT NULL DEFAULT '[]'::jsonb,
          sensitivity VARCHAR(32) NOT NULL,
          permission VARCHAR(64) NOT NULL,
          valid_from DATE NOT NULL,
          valid_to DATE,
          status VARCHAR(20) NOT NULL,
          definition_hash CHAR(64) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(dimension_id, version),
          CONSTRAINT ck_chatbi_dimension_status CHECK (status IN ('draft','active','retired'))
        );

        CREATE TABLE chatbi_join_catalog (
          join_id VARCHAR(64) NOT NULL,
          version INTEGER NOT NULL,
          left_dataset VARCHAR(64) NOT NULL,
          right_dataset VARCHAR(64) NOT NULL,
          join_keys JSONB NOT NULL,
          join_type VARCHAR(16) NOT NULL,
          allowed_metrics JSONB NOT NULL,
          allowed_dimensions JSONB NOT NULL,
          status VARCHAR(20) NOT NULL,
          permission VARCHAR(64) NOT NULL,
          definition_hash CHAR(64) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(join_id, version),
          CONSTRAINT ck_chatbi_join_type CHECK (join_type IN ('inner','left')),
          CONSTRAINT ck_chatbi_join_status CHECK (status IN ('draft','active','retired'))
        );

        CREATE TABLE chatbi_analysis_plans (
          analysis_plan_id VARCHAR(72) PRIMARY KEY,
          tenant_id VARCHAR(64) NOT NULL,
          workspace_id VARCHAR(64) NOT NULL,
          user_id VARCHAR(128) NOT NULL,
          agent_id VARCHAR(64) NOT NULL,
          session_id VARCHAR(128) NOT NULL,
          run_id VARCHAR(128) NOT NULL,
          question_hash CHAR(64) NOT NULL,
          plan_hash CHAR(64) NOT NULL,
          catalog_version VARCHAR(32) NOT NULL,
          plan_json JSONB NOT NULL,
          validation_status VARCHAR(32) NOT NULL,
          validation_errors JSONB NOT NULL DEFAULT '[]'::jsonb,
          status VARCHAR(24) NOT NULL,
          query_hash CHAR(64),
          result_hash CHAR(64),
          created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          executed_at TIMESTAMPTZ,
          CONSTRAINT ck_chatbi_plan_status CHECK (status IN ('draft','clarification_required','validated','rejected','executed','failed'))
        );
        CREATE INDEX idx_chatbi_plan_scope ON chatbi_analysis_plans(tenant_id,workspace_id,user_id,agent_id,created_at DESC);
        CREATE INDEX idx_chatbi_plan_session ON chatbi_analysis_plans(tenant_id,workspace_id,user_id,session_id,created_at DESC);

        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='beta10d_app_runtime') THEN
            GRANT SELECT ON chatbi_metric_catalog,chatbi_dimension_catalog,chatbi_join_catalog TO beta10d_app_runtime;
            GRANT SELECT,INSERT,UPDATE ON chatbi_analysis_plans TO beta10d_app_runtime;
          END IF;
        END $$;
        """
    )

def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='beta10d_app_runtime') THEN
            REVOKE ALL ON chatbi_analysis_plans,chatbi_join_catalog,chatbi_dimension_catalog,chatbi_metric_catalog FROM beta10d_app_runtime;
          END IF;
        END $$;
        DROP TABLE chatbi_analysis_plans;
        DROP TABLE chatbi_join_catalog;
        DROP TABLE chatbi_dimension_catalog;
        DROP TABLE chatbi_metric_catalog;
        """
    )

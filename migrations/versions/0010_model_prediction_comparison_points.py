"""model prediction comparison points

Revision ID: 0010_model_pred_points
Revises: 0009_model_center_governance
Create Date: 2026-07-01
"""
from __future__ import annotations

from alembic import op


revision = "0010_model_pred_points"
down_revision = "0009_model_center_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_prediction_comparison_points (
            id BIGSERIAL PRIMARY KEY,
            model_type VARCHAR(64) NOT NULL DEFAULT '负荷预测模型',
            region VARCHAR(64) NOT NULL DEFAULT '浙江省',
            forecast_time TIMESTAMP NOT NULL,
            active_version VARCHAR(128) NOT NULL,
            candidate_version VARCHAR(128) NOT NULL,
            actual_value DOUBLE PRECISION,
            active_prediction DOUBLE PRECISION,
            candidate_prediction DOUBLE PRECISION,
            diff_value DOUBLE PRECISION,
            granularity VARCHAR(32) NOT NULL DEFAULT '15分钟',
            data_origin VARCHAR(32) NOT NULL DEFAULT 'seed',
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uk_model_prediction_comparison_points UNIQUE (
                model_type, region, forecast_time, active_version, candidate_version
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_model_prediction_comparison_time
        ON model_prediction_comparison_points(forecast_time)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_model_prediction_comparison_versions
        ON model_prediction_comparison_points(active_version, candidate_version)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_model_prediction_comparison_region
        ON model_prediction_comparison_points(model_type, region)
        """
    )


def downgrade() -> None:
    # Productization migrations are intentionally non-destructive in this phase.
    pass

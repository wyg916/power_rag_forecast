"""add Stage1 raw data tables

Revision ID: 0003_stage1_raw_data
Revises: 0002_rag_rbac_audit
Create Date: 2026-06-08
"""
from __future__ import annotations

from alembic import op


revision = "0003_stage1_raw_data"
down_revision = "0002_rag_rbac_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_market (
            id BIGSERIAL PRIMARY KEY,
            market VARCHAR(64),
            node_name VARCHAR(128),
            price_type VARCHAR(32) NOT NULL DEFAULT 'DA',
            datetime TIMESTAMP,
            da_price DOUBLE PRECISION,
            rt_price DOUBLE PRECISION,
            lmp DOUBLE PRECISION,
            source_file TEXT,
            source_row INTEGER,
            raw_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_raw_market_datetime ON raw_market(datetime)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_raw_market_market_type ON raw_market(market, price_type)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_weather (
            id BIGSERIAL PRIMARY KEY,
            point_name VARCHAR(128),
            city VARCHAR(128),
            datetime TIMESTAMP,
            temperature DOUBLE PRECISION,
            humidity DOUBLE PRECISION,
            wind_speed DOUBLE PRECISION,
            source_file TEXT,
            source_row INTEGER,
            raw_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_raw_weather_datetime ON raw_weather(datetime)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_raw_weather_point ON raw_weather(point_name)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_load (
            id BIGSERIAL PRIMARY KEY,
            market VARCHAR(64),
            datetime TIMESTAMP,
            actual_load DOUBLE PRECISION,
            forecast_load DOUBLE PRECISION,
            source_file TEXT,
            source_row INTEGER,
            raw_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_raw_load_datetime ON raw_load(datetime)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_raw_load_market ON raw_load(market)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_renewable (
            id BIGSERIAL PRIMARY KEY,
            market VARCHAR(64),
            datetime TIMESTAMP,
            solar_mw DOUBLE PRECISION,
            wind_mw DOUBLE PRECISION,
            storage_mw DOUBLE PRECISION,
            renewable_total_mw DOUBLE PRECISION,
            source_file TEXT,
            source_row INTEGER,
            raw_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_raw_renewable_datetime ON raw_renewable(datetime)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_raw_renewable_market ON raw_renewable(market)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS feature_importance (
            id BIGSERIAL PRIMARY KEY,
            model_version VARCHAR(128),
            feature VARCHAR(255),
            importance DOUBLE PRECISION,
            rank INTEGER,
            source_file TEXT,
            source_row INTEGER,
            raw_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_feature_importance_model ON feature_importance(model_version)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_feature_importance_rank ON feature_importance(rank)")

    op.execute(
        """
        CREATE OR REPLACE VIEW raw_da_price AS
        SELECT id, market, node_name, datetime, da_price, source_file, source_row, raw_json, created_at, updated_at
        FROM raw_market
        WHERE da_price IS NOT NULL OR price_type = 'DA'
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW raw_rt_price AS
        SELECT id, market, node_name, datetime, rt_price, source_file, source_row, raw_json, created_at, updated_at
        FROM raw_market
        WHERE rt_price IS NOT NULL OR price_type = 'RT'
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW raw_actual_load AS
        SELECT id, market, datetime, actual_load, source_file, source_row, raw_json, created_at, updated_at
        FROM raw_load
        WHERE actual_load IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW raw_forecast_load_selected AS
        SELECT id, market, datetime, forecast_load, source_file, source_row, raw_json, created_at, updated_at
        FROM raw_load
        WHERE forecast_load IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW model_feature_importance AS
        SELECT id, model_version, feature, importance, rank, source_file, source_row, raw_json, created_at
        FROM feature_importance
        """
    )


def downgrade() -> None:
    # Productization migrations are intentionally non-destructive in this phase.
    pass

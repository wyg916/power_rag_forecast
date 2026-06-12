"""initial PostgreSQL schema for core fact tables

Revision ID: 0001_initial_postgres_schema
Revises:
Create Date: 2026-06-01
"""
from __future__ import annotations

from alembic import op


revision = "0001_initial_postgres_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS forecast_runs (
            run_id VARCHAR(64) PRIMARY KEY,
            source_path TEXT,
            forecast_start TIMESTAMP,
            forecast_end TIMESTAMP,
            generated_at TIMESTAMP,
            row_count INTEGER,
            status VARCHAR(32) NOT NULL DEFAULT 'ready',
            summary_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS forecast_results (
            id BIGSERIAL PRIMARY KEY,
            run_id VARCHAR(64) NOT NULL REFERENCES forecast_runs(run_id) ON DELETE CASCADE,
            forecast_datetime TIMESTAMP,
            predicted_price DOUBLE PRECISION,
            corrected_predicted_price DOUBLE PRECISION,
            risk_level VARCHAR(32),
            spike_risk_prob DOUBLE PRECISION,
            forecast_load DOUBLE PRECISION,
            source_row INTEGER,
            raw_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uk_forecast_run_time UNIQUE (run_id, forecast_datetime)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_forecast_results_run_id ON forecast_results(run_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_forecast_results_datetime ON forecast_results(forecast_datetime)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_forecast_results_risk ON forecast_results(risk_level)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_versions (
            id BIGSERIAL PRIMARY KEY,
            model_version VARCHAR(128) NOT NULL UNIQUE,
            model_name VARCHAR(128),
            model_type VARCHAR(64),
            artifact_path TEXT,
            status VARCHAR(32),
            is_active BOOLEAN,
            metrics_json JSONB,
            created_at TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_metrics (
            id BIGSERIAL PRIMARY KEY,
            model_version VARCHAR(128) NOT NULL,
            metric_date DATE,
            mae DOUBLE PRECISION,
            rmse DOUBLE PRECISION,
            r2 DOUBLE PRECISION,
            mape DOUBLE PRECISION,
            peak_error DOUBLE PRECISION,
            sample_count INTEGER,
            metrics_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_metrics_version ON model_metrics(model_version)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_metrics_date ON model_metrics(metric_date)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS task_runs (
            task_id VARCHAR(64) PRIMARY KEY,
            run_id VARCHAR(64),
            task_name VARCHAR(128),
            task_kind VARCHAR(64),
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            payload_json JSONB,
            started_at TIMESTAMP,
            ended_at TIMESTAMP,
            duration_seconds DOUBLE PRECISION,
            error_message TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS task_logs (
            id BIGSERIAL PRIMARY KEY,
            task_id VARCHAR(64),
            run_id VARCHAR(64),
            task_name VARCHAR(128),
            task_kind VARCHAR(64),
            status VARCHAR(32),
            command_json JSONB,
            log_path TEXT,
            log_text TEXT,
            started_at TIMESTAMP,
            ended_at TIMESTAMP,
            duration_seconds DOUBLE PRECISION,
            returncode INTEGER,
            error_message TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_runs_status ON task_runs(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_logs_task_id ON task_logs(task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_logs_run_id ON task_logs(run_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_logs_status ON task_logs(status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_traces (
            trace_id VARCHAR(64) PRIMARY KEY,
            session_id VARCHAR(64),
            question TEXT,
            intent VARCHAR(64),
            answer TEXT,
            tools_json JSONB,
            evidence_json JSONB,
            guard_result_json JSONB,
            trace_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_traces_session ON ai_traces(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_traces_intent ON ai_traces(intent)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_traces_tools_gin ON ai_traces USING GIN (tools_json)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_traces_evidence_gin ON ai_traces USING GIN (evidence_json)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS report_runs (
            report_id VARCHAR(64) PRIMARY KEY,
            run_id VARCHAR(64),
            title VARCHAR(255),
            status VARCHAR(32) NOT NULL DEFAULT 'draft',
            report_type VARCHAR(64),
            file_path TEXT,
            metadata_json JSONB,
            content_json JSONB,
            generated_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS report_reviews (
            id BIGSERIAL PRIMARY KEY,
            report_id VARCHAR(64),
            action VARCHAR(32),
            reviewer VARCHAR(128),
            comment TEXT,
            metadata_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_report_runs_run_id ON report_runs(run_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_report_runs_status ON report_runs(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_report_reviews_report_id ON report_reviews(report_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pv_tariff_rules (
            id BIGSERIAL PRIMARY KEY,
            province VARCHAR(64),
            city VARCHAR(64),
            start_date DATE,
            end_date DATE,
            on_grid_price DOUBLE PRECISION,
            subsidy_start_date DATE,
            subsidy_years DOUBLE PRECISION,
            subsidy_price DOUBLE PRECISION,
            total_price DOUBLE PRECISION,
            remark TEXT,
            source_sheet VARCHAR(128),
            source_row INTEGER,
            raw_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_pv_tariff_rules_region ON pv_tariff_rules(province, city)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_pv_tariff_rules_period ON pv_tariff_rules(start_date, end_date)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pv_policy_files (
            id BIGSERIAL PRIMARY KEY,
            doc_id VARCHAR(64),
            title VARCHAR(255),
            doc_number VARCHAR(128),
            publish_date DATE,
            province VARCHAR(64),
            city VARCHAR(64),
            summary TEXT,
            source_file TEXT,
            source_sheet VARCHAR(128),
            source_row INTEGER,
            raw_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_pv_policy_region ON pv_policy_files(province, city)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_pv_policy_doc_number ON pv_policy_files(doc_number)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pv_station_tariff_check (
            id BIGSERIAL PRIMARY KEY,
            station_id VARCHAR(128),
            station_name VARCHAR(255),
            province VARCHAR(64),
            city VARCHAR(64),
            district VARCHAR(64),
            grid_date DATE,
            system_price DOUBLE PRECISION,
            grid_price DOUBLE PRECISION,
            national_subsidy DOUBLE PRECISION,
            provincial_subsidy DOUBLE PRECISION,
            difference_flag VARCHAR(64),
            remark TEXT,
            source_sheet VARCHAR(128),
            source_row INTEGER,
            raw_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_station_tariff_station ON pv_station_tariff_check(station_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_station_tariff_region ON pv_station_tariff_check(province, city)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_power_price_rules (
            id BIGSERIAL PRIMARY KEY,
            business_month VARCHAR(32),
            province VARCHAR(64),
            city VARCHAR(64),
            power_price DOUBLE PRECISION,
            auxiliary_cost DOUBLE PRECISION,
            total_price DOUBLE PRECISION,
            remark TEXT,
            source_sheet VARCHAR(128),
            source_row INTEGER,
            raw_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_market_power_month ON market_power_price_rules(business_month)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_market_power_region ON market_power_price_rules(province, city)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS southern_grid_tax_rules (
            id BIGSERIAL PRIMARY KEY,
            province VARCHAR(64),
            city VARCHAR(64),
            district VARCHAR(64),
            station_id VARCHAR(128),
            station_name VARCHAR(255),
            deduction_rate DOUBLE PRECISION,
            payment_formula TEXT,
            tax_remark TEXT,
            evidence_json JSONB,
            source_sheet VARCHAR(128),
            source_row INTEGER,
            raw_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_southern_grid_region ON southern_grid_tax_rules(province, city, district)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_southern_grid_station ON southern_grid_tax_rules(station_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pv_tariff_period_rules (
            id BIGSERIAL PRIMARY KEY,
            province_source VARCHAR(128),
            region_name VARCHAR(128),
            province VARCHAR(64),
            city VARCHAR(64),
            combination VARCHAR(128),
            grid_type VARCHAR(128),
            period_1_on_grid_price DOUBLE PRECISION,
            period_1_subsidy_price DOUBLE PRECISION,
            period_1_total_price DOUBLE PRECISION,
            period_2_on_grid_price DOUBLE PRECISION,
            period_2_subsidy_price DOUBLE PRECISION,
            period_2_total_price DOUBLE PRECISION,
            period_3_on_grid_price DOUBLE PRECISION,
            period_3_subsidy_price DOUBLE PRECISION,
            period_3_total_price DOUBLE PRECISION,
            policy_doc_no VARCHAR(128),
            doc_image TEXT,
            source_sheet VARCHAR(128),
            source_row INTEGER,
            raw_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_pv_tariff_period_region ON pv_tariff_period_rules(province, city)")


def downgrade() -> None:
    # Baseline migration is intentionally non-destructive for this productization phase.
    pass

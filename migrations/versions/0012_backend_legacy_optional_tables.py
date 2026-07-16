"""add PostgreSQL compatibility tables for legacy backend workflows

Revision ID: 0012_backend_legacy_tables
Revises: 0011_settings_center_closure
Create Date: 2026-07-09
"""
from __future__ import annotations

from alembic import op


revision = "0012_backend_legacy_tables"
down_revision = "0011_settings_center_closure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(32) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_registry (
            model_version VARCHAR(64) PRIMARY KEY,
            model_role VARCHAR(32) NOT NULL,
            train_start_date DATE,
            train_end_date DATE,
            feature_version VARCHAR(64),
            artifact_path VARCHAR(500) NOT NULL,
            test_mae NUMERIC(12,6),
            test_rmse NUMERIC(12,6),
            peak_rmse NUMERIC(12,6),
            spike_rmse NUMERIC(12,6),
            rolling_rmse NUMERIC(12,6),
            is_active SMALLINT NOT NULL DEFAULT 0,
            status VARCHAR(32) NOT NULL DEFAULT 'candidate',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            activated_at TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_registry_status_active ON model_registry(status, is_active)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_registry_created_at ON model_registry(created_at)")
    op.execute(
        """
        CREATE OR REPLACE VIEW vw_latest_active_model AS
        SELECT *
        FROM model_registry
        WHERE is_active = 1
        ORDER BY activated_at DESC NULLS LAST, created_at DESC
        LIMIT 1
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS prediction_tracking (
            id BIGSERIAL PRIMARY KEY,
            run_id VARCHAR(64) NOT NULL,
            forecast_datetime TIMESTAMP NOT NULL,
            generated_at TIMESTAMP NOT NULL,
            predicted_price NUMERIC(12,4) NOT NULL,
            actual_price NUMERIC(12,4),
            abs_error NUMERIC(12,4),
            pct_error NUMERIC(12,4),
            hour SMALLINT,
            is_peak_hour SMALLINT NOT NULL DEFAULT 0,
            is_spike_risk SMALLINT NOT NULL DEFAULT 0,
            spike_probability NUMERIC(8,6),
            model_version VARCHAR(64) NOT NULL,
            feature_version VARCHAR(64),
            filled_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_prediction_tracking_forecast_datetime ON prediction_tracking(forecast_datetime)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_prediction_tracking_model_version ON prediction_tracking(model_version)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_prediction_tracking_run_id ON prediction_tracking(run_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_prediction_tracking_created_at ON prediction_tracking(created_at)")
    op.execute(
        """
        CREATE OR REPLACE VIEW vw_recent_model_errors AS
        SELECT
            model_version,
            DATE(forecast_datetime) AS forecast_date,
            COUNT(*) AS sample_count,
            AVG(abs_error) AS mae,
            SQRT(AVG(POWER(abs_error, 2))) AS rmse,
            AVG(pct_error) AS mape
        FROM prediction_tracking
        WHERE actual_price IS NOT NULL
        GROUP BY model_version, DATE(forecast_datetime)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_evaluation_runs (
            id BIGSERIAL PRIMARY KEY,
            run_id VARCHAR(64) NOT NULL,
            model_version VARCHAR(64) NOT NULL,
            evaluation_window_start TIMESTAMP,
            evaluation_window_end TIMESTAMP,
            mae NUMERIC(12,6),
            rmse NUMERIC(12,6),
            mape NUMERIC(12,6),
            peak_rmse NUMERIC(12,6),
            spike_rmse NUMERIC(12,6),
            better_than_active SMALLINT NOT NULL DEFAULT 0,
            decision VARCHAR(32) NOT NULL DEFAULT 'candidate',
            details_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_evaluation_runs_model_version ON model_evaluation_runs(model_version)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_evaluation_runs_run_id ON model_evaluation_runs(run_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_evaluation_runs_created_at ON model_evaluation_runs(created_at)")
    op.execute(
        """
        CREATE OR REPLACE VIEW vw_model_comparison AS
        SELECT model_version, decision, mae, rmse, peak_rmse, spike_rmse, created_at
        FROM model_evaluation_runs
        ORDER BY created_at DESC
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoring_metrics (
            id BIGSERIAL PRIMARY KEY,
            run_id VARCHAR(64),
            metric_name VARCHAR(128) NOT NULL,
            metric_value NUMERIC(18,6),
            metric_text VARCHAR(500),
            severity VARCHAR(32) NOT NULL DEFAULT 'info',
            source VARCHAR(64),
            observed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_monitoring_metrics_name_time ON monitoring_metrics(metric_name, observed_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_monitoring_metrics_run_id ON monitoring_metrics(run_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_monitoring_metrics_severity ON monitoring_metrics(severity)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_performance_daily (
            id BIGSERIAL PRIMARY KEY,
            model_version VARCHAR(64) NOT NULL,
            metric_date DATE NOT NULL,
            sample_count INTEGER NOT NULL,
            mae NUMERIC(12,6),
            rmse NUMERIC(12,6),
            mape NUMERIC(12,6),
            peak_rmse NUMERIC(12,6),
            spike_rmse NUMERIC(12,6),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uk_model_perf_daily UNIQUE (model_version, metric_date)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_performance_daily_date ON model_performance_daily(metric_date)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_retrain_jobs (
            id BIGSERIAL PRIMARY KEY,
            job_id VARCHAR(64) NOT NULL UNIQUE,
            trigger_source VARCHAR(64) NOT NULL,
            trigger_reason VARCHAR(500) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            candidate_model_version VARCHAR(64),
            requested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            details TEXT
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_retrain_jobs_status ON model_retrain_jobs(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_retrain_jobs_requested_at ON model_retrain_jobs(requested_at)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_comparison_runs (
            id BIGSERIAL PRIMARY KEY,
            comparison_id VARCHAR(64) NOT NULL UNIQUE,
            candidate_model_version VARCHAR(64) NOT NULL,
            active_model_version VARCHAR(64) NOT NULL,
            decision VARCHAR(32) NOT NULL,
            reason VARCHAR(500),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_comparison_candidate ON model_comparison_runs(candidate_model_version)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_comparison_active ON model_comparison_runs(active_model_version)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_comparison_decision ON model_comparison_runs(decision)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_error_memory (
            id BIGSERIAL PRIMARY KEY,
            model_version VARCHAR(64) NOT NULL,
            hour SMALLINT,
            day_of_week SMALLINT,
            is_peak_hour SMALLINT NOT NULL DEFAULT 0,
            risk_level VARCHAR(16) NOT NULL DEFAULT 'normal',
            load_bucket VARCHAR(32) NOT NULL DEFAULT 'unknown',
            weather_bucket VARCHAR(32) NOT NULL DEFAULT 'unknown',
            sample_count INTEGER NOT NULL DEFAULT 0,
            mae NUMERIC(12,6),
            rmse NUMERIC(12,6),
            bias_mean NUMERIC(12,6),
            bias_median NUMERIC(12,6),
            over_pred_count INTEGER NOT NULL DEFAULT 0,
            under_pred_count INTEGER NOT NULL DEFAULT 0,
            last_updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uk_model_error_memory_scene UNIQUE (
                model_version, hour, day_of_week, is_peak_hour, risk_level, load_bucket, weather_bucket
            )
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_error_memory_model ON model_error_memory(model_version)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_error_memory_scene_lookup ON model_error_memory(model_version, hour, is_peak_hour, sample_count)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_strategy_memory (
            id BIGSERIAL PRIMARY KEY,
            strategy_id VARCHAR(128) NOT NULL UNIQUE,
            model_version VARCHAR(64) NOT NULL,
            feature_set_version VARCHAR(64),
            model_type VARCHAR(64),
            training_window_days INTEGER,
            peak_weight NUMERIC(12,6),
            spike_threshold NUMERIC(12,6),
            alpha NUMERIC(12,6),
            peak_floor NUMERIC(12,6),
            mae NUMERIC(12,6),
            rmse NUMERIC(12,6),
            peak_rmse NUMERIC(12,6),
            spike_rmse NUMERIC(12,6),
            stability_score NUMERIC(12,6),
            is_recommended SMALLINT NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_strategy_memory_model ON model_strategy_memory(model_version)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_strategy_memory_rank ON model_strategy_memory(is_recommended, stability_score, rmse)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS report_approval_runs (
            id BIGSERIAL PRIMARY KEY,
            run_id VARCHAR(64) NOT NULL,
            report_path VARCHAR(500),
            approval_status VARCHAR(32) NOT NULL DEFAULT 'pending',
            reviewer VARCHAR(128),
            review_comment TEXT,
            reviewed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_report_approval_run_id ON report_approval_runs(run_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_report_approval_status ON report_approval_runs(approval_status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_report_review_runs (
            id BIGSERIAL PRIMARY KEY,
            run_id VARCHAR(64) NOT NULL UNIQUE,
            report_path VARCHAR(500),
            review_status VARCHAR(32) NOT NULL DEFAULT 'pending',
            reviewer VARCHAR(128),
            review_comment TEXT,
            reviewed_at TIMESTAMP,
            dispatch_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_report_review_status ON ai_report_review_runs(review_status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_report_review_reviewed_at ON ai_report_review_runs(reviewed_at)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_runs (
            id BIGSERIAL PRIMARY KEY,
            run_id VARCHAR(64) NOT NULL UNIQUE,
            run_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            started_at TIMESTAMP,
            ended_at TIMESTAMP,
            duration_seconds INTEGER,
            error_message TEXT,
            created_by VARCHAR(128),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_analysis_runs_status ON analysis_runs(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_analysis_runs_started_at ON analysis_runs(started_at)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_advice (
            id BIGSERIAL PRIMARY KEY,
            run_id VARCHAR(64) NOT NULL,
            scenario VARCHAR(64) NOT NULL,
            target_hour TIMESTAMP,
            risk_level VARCHAR(32),
            advice_type VARCHAR(64),
            advice_text TEXT NOT NULL,
            evidence_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_strategy_run_id ON strategy_advice(run_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_strategy_target_hour ON strategy_advice(target_hour)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_strategy_scenario ON strategy_advice(scenario)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_chat_sessions (
            id BIGSERIAL PRIMARY KEY,
            session_id VARCHAR(128) NOT NULL UNIQUE,
            user_id VARCHAR(128),
            title VARCHAR(255),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_chat_sessions_updated_at ON ai_chat_sessions(updated_at)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_chat_messages (
            id BIGSERIAL PRIMARY KEY,
            session_id VARCHAR(128) NOT NULL,
            role VARCHAR(32) NOT NULL,
            content TEXT NOT NULL,
            evidence_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_chat_messages_session_id ON ai_chat_messages(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_chat_messages_created_at ON ai_chat_messages(created_at)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS anomaly_explanations (
            id BIGSERIAL PRIMARY KEY,
            run_id VARCHAR(64) NOT NULL,
            target_hour TIMESTAMP,
            anomaly_type VARCHAR(128),
            risk_level VARCHAR(32),
            explanation TEXT NOT NULL,
            recommendation TEXT,
            evidence_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_run_id ON anomaly_explanations(run_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_target_hour ON anomaly_explanations(target_hour)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_risk_level ON anomaly_explanations(risk_level)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_tool_call_logs (
            id BIGSERIAL PRIMARY KEY,
            session_id VARCHAR(128),
            message_id BIGINT,
            tool_name VARCHAR(128) NOT NULL,
            input_json JSONB,
            output_json JSONB,
            success BOOLEAN NOT NULL DEFAULT TRUE,
            error_message TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_tool_call_session ON ai_tool_call_logs(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_tool_call_name ON ai_tool_call_logs(tool_name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_tool_call_created_at ON ai_tool_call_logs(created_at)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_prompt_templates (
            id BIGSERIAL PRIMARY KEY,
            template_key VARCHAR(128) NOT NULL,
            scenario VARCHAR(64),
            role_scope VARCHAR(64),
            version INTEGER NOT NULL DEFAULT 1,
            content TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by VARCHAR(64),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_prompt_template_active ON ai_prompt_templates(template_key, is_active)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_prompt_template_scenario ON ai_prompt_templates(scenario)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_chat_feedback (
            id BIGSERIAL PRIMARY KEY,
            session_id VARCHAR(128),
            trace_id VARCHAR(128),
            rating VARCHAR(16) NOT NULL,
            comment TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_chat_feedback_session_id ON ai_chat_feedback(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_chat_feedback_trace_id ON ai_chat_feedback(trace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_chat_feedback_created_at ON ai_chat_feedback(created_at)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_conversation_state (
            id BIGSERIAL PRIMARY KEY,
            session_id VARCHAR(128) NOT NULL UNIQUE,
            last_intent VARCHAR(128),
            last_topic VARCHAR(128),
            last_focus_time TIMESTAMP,
            last_focus_metric VARCHAR(128),
            last_focus_value VARCHAR(255),
            last_run_id VARCHAR(128),
            last_answer_summary TEXT,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_conversation_state_session ON ai_conversation_state(session_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_answer_feedback (
            id BIGSERIAL PRIMARY KEY,
            trace_id VARCHAR(128),
            session_id VARCHAR(128),
            question TEXT,
            answer TEXT,
            feedback_type VARCHAR(64),
            feedback_comment TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_answer_feedback_trace ON ai_answer_feedback(trace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_answer_feedback_session ON ai_answer_feedback(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_answer_feedback_type ON ai_answer_feedback(feedback_type)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_qa_test_cases (
            id BIGSERIAL PRIMARY KEY,
            question TEXT NOT NULL,
            expected_intent VARCHAR(128),
            expected_tool VARCHAR(128),
            expected_keywords TEXT,
            category VARCHAR(128),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_qa_test_cases_active ON ai_qa_test_cases(is_active)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_qa_test_cases_category ON ai_qa_test_cases(category)")


def downgrade() -> None:
    # Productization migrations are intentionally non-destructive in this phase.
    pass


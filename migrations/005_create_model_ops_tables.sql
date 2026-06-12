CREATE TABLE IF NOT EXISTS model_performance_daily (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    model_version VARCHAR(64) NOT NULL,
    metric_date DATE NOT NULL,
    sample_count INT NOT NULL,
    mae DECIMAL(12,6) NULL,
    rmse DECIMAL(12,6) NULL,
    mape DECIMAL(12,6) NULL,
    peak_rmse DECIMAL(12,6) NULL,
    spike_rmse DECIMAL(12,6) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_model_perf_daily (model_version, metric_date),
    INDEX idx_model_performance_daily_date (metric_date)
);

CREATE TABLE IF NOT EXISTS model_retrain_jobs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    job_id VARCHAR(64) NOT NULL UNIQUE,
    trigger_source VARCHAR(64) NOT NULL,
    trigger_reason VARCHAR(500) NOT NULL,
    status VARCHAR(32) DEFAULT 'pending',
    candidate_model_version VARCHAR(64) NULL,
    requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    finished_at DATETIME NULL,
    details TEXT NULL,
    INDEX idx_model_retrain_jobs_status (status),
    INDEX idx_model_retrain_jobs_requested_at (requested_at)
);

CREATE TABLE IF NOT EXISTS model_comparison_runs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    comparison_id VARCHAR(64) NOT NULL UNIQUE,
    candidate_model_version VARCHAR(64) NOT NULL,
    active_model_version VARCHAR(64) NOT NULL,
    decision VARCHAR(32) NOT NULL,
    reason VARCHAR(500) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_model_comparison_candidate (candidate_model_version),
    INDEX idx_model_comparison_active (active_model_version),
    INDEX idx_model_comparison_decision (decision)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    actor VARCHAR(128) NOT NULL,
    action VARCHAR(128) NOT NULL,
    target_type VARCHAR(64) NULL,
    target_id VARCHAR(128) NULL,
    details TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_logs_action_time (action, created_at),
    INDEX idx_audit_logs_actor_time (actor, created_at)
);

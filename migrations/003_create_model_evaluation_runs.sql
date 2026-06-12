CREATE TABLE IF NOT EXISTS model_evaluation_runs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    run_id VARCHAR(64) NOT NULL,
    model_version VARCHAR(64) NOT NULL,
    evaluation_window_start DATETIME NULL,
    evaluation_window_end DATETIME NULL,
    mae DECIMAL(12,6) NULL,
    rmse DECIMAL(12,6) NULL,
    mape DECIMAL(12,6) NULL,
    peak_rmse DECIMAL(12,6) NULL,
    spike_rmse DECIMAL(12,6) NULL,
    better_than_active TINYINT DEFAULT 0,
    decision VARCHAR(32) DEFAULT 'candidate',
    details_json JSON NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_model_evaluation_runs_model_version (model_version),
    INDEX idx_model_evaluation_runs_run_id (run_id),
    INDEX idx_model_evaluation_runs_created_at (created_at)
);

CREATE OR REPLACE VIEW vw_model_comparison AS
SELECT
    model_version,
    decision,
    mae,
    rmse,
    peak_rmse,
    spike_rmse,
    created_at
FROM model_evaluation_runs
ORDER BY created_at DESC;

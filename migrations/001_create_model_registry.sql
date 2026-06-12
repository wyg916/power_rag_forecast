CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(32) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_registry (
    model_version VARCHAR(64) PRIMARY KEY,
    model_role VARCHAR(32) NOT NULL,
    train_start_date DATE NULL,
    train_end_date DATE NULL,
    feature_version VARCHAR(64) NULL,
    artifact_path VARCHAR(500) NOT NULL,
    test_mae DECIMAL(12,6) NULL,
    test_rmse DECIMAL(12,6) NULL,
    peak_rmse DECIMAL(12,6) NULL,
    spike_rmse DECIMAL(12,6) NULL,
    rolling_rmse DECIMAL(12,6) NULL,
    is_active TINYINT DEFAULT 0,
    status VARCHAR(32) DEFAULT 'candidate',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    activated_at DATETIME NULL,
    INDEX idx_model_registry_status_active (status, is_active),
    INDEX idx_model_registry_created_at (created_at)
);

CREATE OR REPLACE VIEW vw_latest_active_model AS
SELECT *
FROM model_registry
WHERE is_active = 1
ORDER BY activated_at DESC, created_at DESC
LIMIT 1;

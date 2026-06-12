CREATE TABLE IF NOT EXISTS monitoring_metrics (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    run_id VARCHAR(64) NULL,
    metric_name VARCHAR(128) NOT NULL,
    metric_value DECIMAL(18,6) NULL,
    metric_text VARCHAR(500) NULL,
    severity VARCHAR(32) DEFAULT 'info',
    source VARCHAR(64) NULL,
    observed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_monitoring_metrics_name_time (metric_name, observed_at),
    INDEX idx_monitoring_metrics_run_id (run_id),
    INDEX idx_monitoring_metrics_severity (severity)
);

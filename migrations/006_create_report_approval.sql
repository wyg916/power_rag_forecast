CREATE TABLE IF NOT EXISTS report_approval_runs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    run_id VARCHAR(64) NOT NULL,
    report_path VARCHAR(500) NULL,
    approval_status VARCHAR(32) DEFAULT 'pending',
    reviewer VARCHAR(128) NULL,
    review_comment TEXT NULL,
    reviewed_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_report_approval_run_id (run_id),
    INDEX idx_report_approval_status (approval_status)
);

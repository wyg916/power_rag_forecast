CREATE TABLE IF NOT EXISTS ai_report_review_runs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    run_id VARCHAR(64) NOT NULL,
    report_path VARCHAR(500) NULL,
    review_status VARCHAR(32) DEFAULT 'pending',
    reviewer VARCHAR(128) NULL,
    review_comment TEXT NULL,
    reviewed_at DATETIME NULL,
    dispatch_allowed TINYINT(1) DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_ai_report_review_run_id (run_id),
    INDEX idx_ai_report_review_status (review_status),
    INDEX idx_ai_report_review_reviewed_at (reviewed_at)
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    run_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    started_at DATETIME NULL,
    ended_at DATETIME NULL,
    duration_seconds INT NULL,
    error_message TEXT NULL,
    created_by VARCHAR(128) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_analysis_runs_run_id (run_id),
    KEY idx_analysis_runs_status (status),
    KEY idx_analysis_runs_started_at (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS strategy_advice (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    scenario VARCHAR(64) NOT NULL,
    target_hour DATETIME NULL,
    risk_level VARCHAR(32) NULL,
    advice_type VARCHAR(64) NULL,
    advice_text TEXT NOT NULL,
    evidence_json JSON NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_strategy_run_id (run_id),
    KEY idx_strategy_target_hour (target_hour),
    KEY idx_strategy_scenario (scenario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ai_chat_sessions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(128) NOT NULL,
    user_id VARCHAR(128) NULL,
    title VARCHAR(255) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_ai_chat_sessions_session_id (session_id),
    KEY idx_ai_chat_sessions_updated_at (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ai_chat_messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(128) NOT NULL,
    role VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    evidence_json JSON NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ai_chat_messages_session_id (session_id),
    KEY idx_ai_chat_messages_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS anomaly_explanations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    target_hour DATETIME NULL,
    anomaly_type VARCHAR(128) NULL,
    risk_level VARCHAR(32) NULL,
    explanation TEXT NOT NULL,
    recommendation TEXT NULL,
    evidence_json JSON NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_anomaly_run_id (run_id),
    KEY idx_anomaly_target_hour (target_hour),
    KEY idx_anomaly_risk_level (risk_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS report_reviews (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    report_id VARCHAR(128) NOT NULL,
    run_id VARCHAR(64) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    reviewer VARCHAR(128) NULL,
    review_comment TEXT NULL,
    version INT DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_report_reviews_report_id (report_id),
    KEY idx_report_reviews_run_id (run_id),
    KEY idx_report_reviews_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


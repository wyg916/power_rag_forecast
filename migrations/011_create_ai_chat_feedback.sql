CREATE TABLE IF NOT EXISTS ai_chat_feedback (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(128),
    trace_id VARCHAR(128),
    rating VARCHAR(16) NOT NULL,
    comment TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session_id (session_id),
    INDEX idx_trace_id (trace_id),
    INDEX idx_created_at (created_at)
);

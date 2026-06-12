CREATE TABLE IF NOT EXISTS ai_conversation_state (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_id VARCHAR(128) NOT NULL UNIQUE,
    last_intent VARCHAR(128),
    last_topic VARCHAR(128),
    last_focus_time DATETIME NULL,
    last_focus_metric VARCHAR(128),
    last_focus_value VARCHAR(255),
    last_run_id VARCHAR(128),
    last_answer_summary TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_ai_conversation_state_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ai_answer_feedback (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    trace_id VARCHAR(128),
    session_id VARCHAR(128),
    question TEXT,
    answer TEXT,
    feedback_type VARCHAR(64),
    feedback_comment TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ai_answer_feedback_trace (trace_id),
    INDEX idx_ai_answer_feedback_session (session_id),
    INDEX idx_ai_answer_feedback_type (feedback_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ai_qa_test_cases (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    question TEXT NOT NULL,
    expected_intent VARCHAR(128),
    expected_tool VARCHAR(128),
    expected_keywords TEXT,
    category VARCHAR(128),
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ai_qa_test_cases_active (is_active),
    INDEX idx_ai_qa_test_cases_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

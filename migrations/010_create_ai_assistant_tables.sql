CREATE TABLE IF NOT EXISTS ai_tool_call_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(128) NULL,
    message_id BIGINT NULL,
    tool_name VARCHAR(128) NOT NULL,
    input_json JSON NULL,
    output_json JSON NULL,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ai_tool_call_session (session_id),
    KEY idx_ai_tool_call_name (tool_name),
    KEY idx_ai_tool_call_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ai_prompt_templates (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    template_key VARCHAR(128) NOT NULL,
    scenario VARCHAR(64) NULL,
    role_scope VARCHAR(64) NULL,
    version INT DEFAULT 1,
    content TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_by VARCHAR(64) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ai_prompt_template_active (template_key, is_active),
    KEY idx_ai_prompt_template_scenario (scenario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


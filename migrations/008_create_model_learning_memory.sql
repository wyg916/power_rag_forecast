CREATE TABLE IF NOT EXISTS model_error_memory (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    model_version VARCHAR(64) NOT NULL,
    hour TINYINT NULL,
    day_of_week TINYINT NULL,
    is_peak_hour TINYINT DEFAULT 0,
    risk_level VARCHAR(16) DEFAULT 'normal',
    load_bucket VARCHAR(32) DEFAULT 'unknown',
    weather_bucket VARCHAR(32) DEFAULT 'unknown',
    sample_count INT NOT NULL DEFAULT 0,
    mae DECIMAL(12,6) NULL,
    rmse DECIMAL(12,6) NULL,
    bias_mean DECIMAL(12,6) NULL,
    bias_median DECIMAL(12,6) NULL,
    over_pred_count INT DEFAULT 0,
    under_pred_count INT DEFAULT 0,
    last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_model_error_memory_scene (
        model_version, hour, day_of_week, is_peak_hour, risk_level, load_bucket, weather_bucket
    ),
    INDEX idx_model_error_memory_model (model_version),
    INDEX idx_model_error_memory_scene_lookup (model_version, hour, is_peak_hour, sample_count)
);

CREATE TABLE IF NOT EXISTS model_strategy_memory (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    strategy_id VARCHAR(128) NOT NULL UNIQUE,
    model_version VARCHAR(64) NOT NULL,
    feature_set_version VARCHAR(64) NULL,
    model_type VARCHAR(64) NULL,
    training_window_days INT NULL,
    peak_weight DECIMAL(12,6) NULL,
    spike_threshold DECIMAL(12,6) NULL,
    alpha DECIMAL(12,6) NULL,
    peak_floor DECIMAL(12,6) NULL,
    mae DECIMAL(12,6) NULL,
    rmse DECIMAL(12,6) NULL,
    peak_rmse DECIMAL(12,6) NULL,
    spike_rmse DECIMAL(12,6) NULL,
    stability_score DECIMAL(12,6) NULL,
    is_recommended TINYINT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_model_strategy_memory_model (model_version),
    INDEX idx_model_strategy_memory_rank (is_recommended, stability_score, rmse)
);

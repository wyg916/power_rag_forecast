CREATE TABLE IF NOT EXISTS prediction_tracking (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    run_id VARCHAR(64) NOT NULL,
    forecast_datetime DATETIME NOT NULL,
    generated_at DATETIME NOT NULL,
    predicted_price DECIMAL(12,4) NOT NULL,
    actual_price DECIMAL(12,4) NULL,
    abs_error DECIMAL(12,4) NULL,
    pct_error DECIMAL(12,4) NULL,
    hour TINYINT NULL,
    is_peak_hour TINYINT DEFAULT 0,
    is_spike_risk TINYINT DEFAULT 0,
    spike_probability DECIMAL(8,6) NULL,
    model_version VARCHAR(64) NOT NULL,
    feature_version VARCHAR(64) NULL,
    filled_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_prediction_tracking_forecast_datetime (forecast_datetime),
    INDEX idx_prediction_tracking_model_version (model_version),
    INDEX idx_prediction_tracking_run_id (run_id),
    INDEX idx_prediction_tracking_created_at (created_at)
);

CREATE OR REPLACE VIEW vw_recent_model_errors AS
SELECT
    model_version,
    DATE(forecast_datetime) AS forecast_date,
    COUNT(*) AS sample_count,
    AVG(abs_error) AS mae,
    SQRT(AVG(POW(abs_error, 2))) AS rmse,
    AVG(pct_error) AS mape
FROM prediction_tracking
WHERE actual_price IS NOT NULL
GROUP BY model_version, DATE(forecast_datetime);

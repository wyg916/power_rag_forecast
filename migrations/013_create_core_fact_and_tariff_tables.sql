CREATE TABLE IF NOT EXISTS forecast_runs (
    run_id VARCHAR(64) NOT NULL PRIMARY KEY,
    source_path TEXT NULL,
    forecast_start DATETIME NULL,
    forecast_end DATETIME NULL,
    generated_at DATETIME NULL,
    row_count INT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'ready',
    summary_json LONGTEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS forecast_results (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    forecast_datetime DATETIME NULL,
    predicted_price DOUBLE NULL,
    corrected_predicted_price DOUBLE NULL,
    risk_level VARCHAR(32) NULL,
    spike_risk_prob DOUBLE NULL,
    forecast_load DOUBLE NULL,
    source_row INT NULL,
    raw_json LONGTEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_forecast_run_time (run_id, forecast_datetime),
    KEY idx_forecast_results_run_id (run_id),
    KEY idx_forecast_results_datetime (forecast_datetime),
    KEY idx_forecast_results_risk (risk_level)
);

CREATE TABLE IF NOT EXISTS model_versions (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    model_version VARCHAR(128) NOT NULL,
    model_name VARCHAR(128) NULL,
    model_type VARCHAR(64) NULL,
    artifact_path TEXT NULL,
    status VARCHAR(32) NULL,
    is_active TINYINT NULL,
    metrics_json LONGTEXT NULL,
    created_at DATETIME NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_model_versions_version (model_version)
);

CREATE TABLE IF NOT EXISTS model_metrics (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    model_version VARCHAR(128) NOT NULL,
    metric_date DATE NULL,
    mae DOUBLE NULL,
    rmse DOUBLE NULL,
    r2 DOUBLE NULL,
    mape DOUBLE NULL,
    peak_error DOUBLE NULL,
    sample_count INT NULL,
    metrics_json LONGTEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_model_metrics_version (model_version),
    KEY idx_model_metrics_date (metric_date)
);

CREATE TABLE IF NOT EXISTS task_logs (
    task_id VARCHAR(64) NOT NULL PRIMARY KEY,
    run_id VARCHAR(64) NULL,
    task_name VARCHAR(128) NULL,
    task_kind VARCHAR(64) NULL,
    status VARCHAR(32) NULL,
    command_json LONGTEXT NULL,
    log_path TEXT NULL,
    started_at DATETIME NULL,
    ended_at DATETIME NULL,
    duration_seconds DOUBLE NULL,
    returncode INT NULL,
    error_message TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_task_logs_run_id (run_id),
    KEY idx_task_logs_status (status)
);

CREATE TABLE IF NOT EXISTS ai_traces (
    trace_id VARCHAR(64) NOT NULL PRIMARY KEY,
    session_id VARCHAR(64) NULL,
    question TEXT NULL,
    intent VARCHAR(64) NULL,
    answer LONGTEXT NULL,
    tools_json LONGTEXT NULL,
    evidence_json LONGTEXT NULL,
    guard_result_json LONGTEXT NULL,
    trace_json LONGTEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ai_traces_session (session_id),
    KEY idx_ai_traces_intent (intent)
);

CREATE TABLE IF NOT EXISTS pv_tariff_rules (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    province VARCHAR(64) NULL,
    city VARCHAR(64) NULL,
    start_date DATE NULL,
    end_date DATE NULL,
    on_grid_price DOUBLE NULL,
    subsidy_start_date DATE NULL,
    subsidy_years DOUBLE NULL,
    subsidy_price DOUBLE NULL,
    total_price DOUBLE NULL,
    remark TEXT NULL,
    source_sheet VARCHAR(128) NULL,
    source_row INT NULL,
    raw_json LONGTEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_pv_tariff_rules_region (province, city),
    KEY idx_pv_tariff_rules_period (start_date, end_date)
);

CREATE TABLE IF NOT EXISTS pv_policy_files (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    doc_id VARCHAR(64) NULL,
    title VARCHAR(255) NULL,
    doc_number VARCHAR(128) NULL,
    publish_date DATE NULL,
    province VARCHAR(64) NULL,
    city VARCHAR(64) NULL,
    summary LONGTEXT NULL,
    source_file TEXT NULL,
    source_sheet VARCHAR(128) NULL,
    source_row INT NULL,
    raw_json LONGTEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_pv_policy_region (province, city),
    KEY idx_pv_policy_doc_number (doc_number)
);

CREATE TABLE IF NOT EXISTS pv_station_tariff_check (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    station_id VARCHAR(128) NULL,
    station_name VARCHAR(255) NULL,
    province VARCHAR(64) NULL,
    city VARCHAR(64) NULL,
    district VARCHAR(64) NULL,
    grid_date DATE NULL,
    system_price DOUBLE NULL,
    grid_price DOUBLE NULL,
    national_subsidy DOUBLE NULL,
    provincial_subsidy DOUBLE NULL,
    difference_flag VARCHAR(64) NULL,
    remark TEXT NULL,
    source_sheet VARCHAR(128) NULL,
    source_row INT NULL,
    raw_json LONGTEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_station_tariff_station (station_id),
    KEY idx_station_tariff_region (province, city)
);

CREATE TABLE IF NOT EXISTS market_power_price_rules (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    business_month VARCHAR(32) NULL,
    province VARCHAR(64) NULL,
    city VARCHAR(64) NULL,
    power_price DOUBLE NULL,
    auxiliary_cost DOUBLE NULL,
    total_price DOUBLE NULL,
    remark TEXT NULL,
    source_sheet VARCHAR(128) NULL,
    source_row INT NULL,
    raw_json LONGTEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_market_power_month (business_month),
    KEY idx_market_power_region (province, city)
);

CREATE TABLE IF NOT EXISTS southern_grid_tax_rules (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    province VARCHAR(64) NULL,
    city VARCHAR(64) NULL,
    district VARCHAR(64) NULL,
    station_id VARCHAR(128) NULL,
    station_name VARCHAR(255) NULL,
    deduction_rate DOUBLE NULL,
    payment_formula TEXT NULL,
    tax_remark TEXT NULL,
    evidence_json LONGTEXT NULL,
    source_sheet VARCHAR(128) NULL,
    source_row INT NULL,
    raw_json LONGTEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_southern_grid_region (province, city, district),
    KEY idx_southern_grid_station (station_id)
);

CREATE TABLE IF NOT EXISTS pv_tariff_period_rules (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    province_source VARCHAR(128) NULL,
    region_name VARCHAR(128) NULL,
    province VARCHAR(64) NULL,
    city VARCHAR(64) NULL,
    combination VARCHAR(128) NULL,
    grid_type VARCHAR(128) NULL,
    period_1_on_grid_price DOUBLE NULL,
    period_1_subsidy_price DOUBLE NULL,
    period_1_total_price DOUBLE NULL,
    period_2_on_grid_price DOUBLE NULL,
    period_2_subsidy_price DOUBLE NULL,
    period_2_total_price DOUBLE NULL,
    period_3_on_grid_price DOUBLE NULL,
    period_3_subsidy_price DOUBLE NULL,
    period_3_total_price DOUBLE NULL,
    policy_doc_no VARCHAR(128) NULL,
    doc_image TEXT NULL,
    source_sheet VARCHAR(128) NULL,
    source_row INT NULL,
    raw_json LONGTEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_pv_tariff_period_region (province, city)
);

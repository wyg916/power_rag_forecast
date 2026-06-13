# P2 Backtest Report

- created_at: 2026-06-13T13:30:26
- acceptable_for_backtest: True
- leakage_high_risk_count: 0
- spike_threshold: 149.37279159999994

## Baseline Methods

- persistence_24h: 使用前一天同小时价格 da_price_lag_24 作为预测。
- rolling_same_hour_7d: 使用过去 7 天同小时价格均值作为预测。
- legacy_active_model: 可选包装 model_ops.active_model_loader 的当前 active legacy 模型；不可用时只记录 warning。

## Warnings

- validation: legacy active model schema mismatch; skipped for fair backtest. missing_expected_features=['year', 'is_month_start', 'is_month_end', 'doy_sin', 'doy_cos', 'forecast_issue_lead_hours', 'is_valley_hour', 'is_transition_hour', 'forecast_load_change_1h_safe', 'forecast_load_change_24h_safe', 'forecast_vs_hist24_ratio', 'forecast_load_change_1h_x_peak', 'forecast_load_change_24h_x_peak', 'da_price_hist_hour_mean', 'da_price_hist_hour_std', 'da_price_hist_dow_mean', 'da_price_hist_month_mean', 'da_price_hist_weekend_mean', 'da_price_lag_6', 'da_price_lag_12'], total_missing=100
- test: legacy active model schema mismatch; skipped for fair backtest. missing_expected_features=['year', 'is_month_start', 'is_month_end', 'doy_sin', 'doy_cos', 'forecast_issue_lead_hours', 'is_valley_hour', 'is_transition_hour', 'forecast_load_change_1h_safe', 'forecast_load_change_24h_safe', 'forecast_vs_hist24_ratio', 'forecast_load_change_1h_x_peak', 'forecast_load_change_24h_x_peak', 'da_price_hist_hour_mean', 'da_price_hist_hour_std', 'da_price_hist_dow_mean', 'da_price_hist_month_mean', 'da_price_hist_weekend_mean', 'da_price_lag_6', 'da_price_lag_12'], total_missing=100

## Overall Metrics

- validation / persistence_24h: rows=720, MAE=18.843595069444444, RMSE=30.050441718651506, MAPE=31.0986443904978, R2=0.47663396839886585
- validation / rolling_same_hour_7d: rows=720, MAE=21.88089577559524, RMSE=36.19413866867949, MAPE=36.005685639543984, R2=0.24075786207720673
- test / persistence_24h: rows=721, MAE=34.29408390152566, RMSE=93.67125526177168, MAPE=35.302029921714656, R2=0.3286761290611552
- test / rolling_same_hour_7d: rows=721, MAE=55.49389364473945, RMSE=116.244296436898, MAPE=74.36970283314702, R2=-0.033862341551309516

## Baseline Comparison

- validation / rolling_same_hour_7d vs persistence_24h: RMSE delta=6.143696950027987, better=False
- test / rolling_same_hour_7d vs persistence_24h: RMSE delta=22.57304117512632, better=False

## Scenario Notes

- 后续模型优化必须同时对比 overall、peak、spike、extreme_weather 和 per-hour 指标。
- 当前报告仅建立可复现 baseline/backtest，不代表模型调参或模型替换。
